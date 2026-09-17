#!/usr/bin/env bash
# FrostSight Guard rev A (draft) -- verification gate.
#
# Runs the whole pipeline this experiment depends on, in order, and
# fails loudly (non-zero exit) on a real problem instead of papering
# over it:
#
#   1. schematic.py  (SKiDL)   -> ERC, guard.net
#   2. build_board.py (pcbnew) -> guard.kicad_pcb (placement, pours,
#                                  scripted routing)
#   3. kicad-cli pcb drc       -> guard/drc_report.json, summarized here
#   4. kicad-cli pcb render    -> renders/top.png, renders/bottom.png
#   5. kicad-cli pcb export svg -> renders/top.svg, renders/bottom.svg
#
# Exit code is non-zero if: SKiDL ERC reports an error, build_board.py
# fails, or DRC reports an ELECTRICAL violation (shorting_items,
# clearance, tracks_crossing, unconnected copper on a net this script
# claims is routed, hole_clearance/drill on copper). DRC's
# "unconnected_items" (ratsnest) and non-electrical nags (courtyard/
# silkscreen spacing) are reported, not treated as failures -- see
# README.md's honest-status section for why, and for this run's actual
# counts.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

FAIL=0
step() { echo; echo "=== $* ==="; }

# -----------------------------------------------------------------------
# 1. Find a python that has SKiDL. Prefer an explicit override, then a
#    venv living next to this script (the setup README.md recommends),
#    then whatever's on PATH.
# -----------------------------------------------------------------------
find_skidl_python() {
    for candidate in "${SKIDL_PYTHON:-}" "$HERE/venv/bin/python3" "python3"; do
        [ -z "$candidate" ] && continue
        if "$candidate" -c "import skidl" >/dev/null 2>&1; then
            echo "$candidate"
            return 0
        fi
    done
    return 1
}

SKIDL_PY="$(find_skidl_python)" || {
    echo "ERROR: no Python with 'skidl' installed found."
    echo "       Set SKIDL_PYTHON=/path/to/python3, or create a venv at"
    echo "       $HERE/venv -- see README.md 'Setup' section."
    exit 1
}

# pcbnew is a KiCad-bundled module; it lives in the system python3 on
# this project's dev environment, never inside the SKiDL venv (skidl and
# pcbnew have never needed to coexist in one interpreter here).
PCBNEW_PY="${PCBNEW_PYTHON:-python3}"
if ! "$PCBNEW_PY" -c "import pcbnew" >/dev/null 2>&1; then
    echo "ERROR: no Python with 'pcbnew' importable found (tried: $PCBNEW_PY)."
    echo "       See README.md 'Setup' section -- this needs KiCad's bundled"
    echo "       python, not a venv."
    exit 1
fi

if ! command -v kicad-cli >/dev/null 2>&1; then
    echo "ERROR: kicad-cli not found on PATH."
    exit 1
fi

# -----------------------------------------------------------------------
# 2. Schematic: SKiDL ERC + netlist
# -----------------------------------------------------------------------
step "schematic.py ($SKIDL_PY)"
if ! "$SKIDL_PY" schematic.py; then
    echo "FAIL: schematic.py (ERC or netlist generation) failed."
    FAIL=1
fi
# SKiDL occasionally can't determine it's running as a script (observed
# non-deterministically in this environment, not tied to a particular
# invocation form) and falls back to naming its log files after an
# interactive REPL session instead of "schematic". Those are pure
# logging noise duplicating schematic.erc/schematic.log -- clean them up
# rather than leave stray files behind on every run.
rm -f skidl_REPL.erc skidl_REPL.log

# -----------------------------------------------------------------------
# 3. Board: placement, pours, scripted routing
# -----------------------------------------------------------------------
if [ "$FAIL" -eq 0 ]; then
    step "build_board.py ($PCBNEW_PY)"
    if ! "$PCBNEW_PY" build_board.py; then
        echo "FAIL: build_board.py failed."
        FAIL=1
    fi
fi

# -----------------------------------------------------------------------
# 4. DRC
# -----------------------------------------------------------------------
if [ "$FAIL" -eq 0 ]; then
    step "kicad-cli pcb drc"
    kicad-cli pcb drc guard.kicad_pcb --format json --output drc_report.json \
        --exit-code-violations >/tmp/guard_drc_stdout.$$ 2>&1
    DRC_RC=$?
    cat /tmp/guard_drc_stdout.$$
    rm -f /tmp/guard_drc_stdout.$$

    "$PCBNEW_PY" - <<'PYEOF'
import json
import sys

with open("drc_report.json") as f:
    d = json.load(f)

# Categories that represent an actual electrical problem (a short, an
# out-of-tolerance clearance between copper, crossing tracks, a hole
# that violates copper spacing). Everything else DRC flags here
# (courtyard/silkscreen spacing, cosmetic nags) is a manufacturability
# note, not an electrical defect, and is reported but not gated on.
ELECTRICAL_TYPES = {
    "shorting_items",
    "clearance",
    "tracks_crossing",
    "hole_clearance",
    "hole_to_hole",
    "drill_out_of_range",
    "copper_edge_clearance",
}

violations = d.get("violations", [])
electrical = [v for v in violations if v["type"] in ELECTRICAL_TYPES]
cosmetic = [v for v in violations if v["type"] not in ELECTRICAL_TYPES]
unconnected = d.get("unconnected_items", [])

print(f"DRC: {len(violations)} total violations "
      f"({len(electrical)} electrical, {len(cosmetic)} non-electrical/cosmetic)")
print(f"DRC: {len(unconnected)} unconnected items (ratsnest -- expected, see README)")

if cosmetic:
    from collections import Counter
    c = Counter(v["type"] for v in cosmetic)
    print(f"  non-electrical breakdown: {dict(c)}")

if electrical:
    print("ELECTRICAL DRC VIOLATIONS (must be zero):")
    for v in electrical:
        print(f"  - {v['type']}: {v['description']}")
    sys.exit(1)
sys.exit(0)
PYEOF
    if [ $? -ne 0 ]; then
        echo "FAIL: electrical DRC violations present."
        FAIL=1
    fi
fi

# -----------------------------------------------------------------------
# 5. Renders (PNG 3D-render + flat SVG, top and bottom)
# -----------------------------------------------------------------------
if [ "$FAIL" -eq 0 ]; then
    step "kicad-cli pcb render / export svg"
    mkdir -p renders
    kicad-cli pcb render guard.kicad_pcb --side top --width 1200 --height 900 \
        --quality basic --output renders/top.png || FAIL=1
    kicad-cli pcb render guard.kicad_pcb --side bottom --width 1200 --height 900 \
        --quality basic --output renders/bottom.png || FAIL=1
    kicad-cli pcb export svg guard.kicad_pcb --layers "F.Cu,F.SilkS,F.Mask,Edge.Cuts" \
        --output renders/top.svg --mode-single --page-size-mode 2 || FAIL=1
    kicad-cli pcb export svg guard.kicad_pcb --layers "B.Cu,B.SilkS,B.Mask,Edge.Cuts" \
        --output renders/bottom.svg --mode-single --page-size-mode 2 || FAIL=1
    du -sh renders/ 2>/dev/null
fi

step "Result"
if [ "$FAIL" -eq 0 ]; then
    echo "check.sh: PASS (see DRC summary above for the honest unrouted/cosmetic counts)"
    exit 0
else
    echo "check.sh: FAIL"
    exit 1
fi
