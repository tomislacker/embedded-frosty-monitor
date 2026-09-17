# FrostSight Guard rev A (draft) -- PCB (experimental)

> **This is an unreviewed draft. It has not been checked by a human EE and
> must not be fabricated as-is.** See
> [docs/compliance.md](../../docs/compliance.md) for the certification
> context this board eventually has to clear, and get a professional EE
> review before sending anything here to a fab. This whole `pcb/guard/`
> tree is an experiment in agent-driven PCB design with a scripted
> verification loop (SKiDL schematic -> pcbnew layout -> `kicad-cli` DRC
> + renders) -- it is deliberately optimized for *reviewability*, not for
> being fab-ready out of the box.

This is the first custom PCB for the Guard tier described in
[docs/product-line.md](../../docs/product-line.md) (Tier 1): a permanent,
every-machine monitor board built around a pre-certified ESP32-C3-MINI-1
module. SELV only -- nothing above 5V ever touches this board.

## Honest status

**What's done:**

- A complete SKiDL schematic ([`schematic.py`](schematic.py)) covering
  every circuit block in the spec: MCU, USB-C power+data with ESD
  protection, 3.3V regulation, CT current-sense front end, 2x DS18B20
  headers, drip-counter header, status/alert LEDs, ack/BOOT/RESET
  buttons, I2C (Qwiic) and UART expansion headers, 2x M3 mounting holes.
- SKiDL ERC passes clean: **0 errors, 0 warnings** (two expected
  advisory warnings are pre-empted with documented, reviewed waivers --
  see the ERC section at the bottom of `schematic.py`).
- A generated KiCad netlist (`guard.net`) and a from-scratch `.kicad_pcb`
  ([`build_board.py`](build_board.py)) with a deliberate, documented
  placement for all 43 components, a ground pour on both copper layers,
  an antenna keep-out rule area, and a scripted attempt at routing the
  short, unambiguous connections.
- `kicad-cli pcb drc` on the routed board: **0 electrical violations**
  (no shorting, no copper clearance violations, no crossing tracks, no
  out-of-range drills/holes). 3 non-electrical DRC nags remain --
  1 courtyard overlap (a mounting hole's 3.45mm-radius assembly-exclusion
  circle just can't clear everything on a board this dense) and 2
  silkscreen-clipped-by-edge nags on the CT jack's own library
  silkscreen, which is expected for a connector whose body intentionally
  overhangs the board edge. Full detail: `drc_report.json`, or run
  `check.sh` yourself.
- Renders inspected and iterated on twice: the first pass had the USB-C
  connector's mating face sitting ~2mm inboard of the board edge instead
  of flush with it; the second pass (current state) fixed that. See
  `renders/top.png` / `renders/bottom.png` / `.svg`.
- A [`bom.csv`](bom.csv) with per-line LCSC estimates and a rollup
  compared against the tier's cost targets.

**What's not done / known limitations:**

- **Routing is partial, on purpose.** The scripted router in
  `build_board.py` only commits a track when it's confident the hop is
  short and won't clip a foreign pad, cross another net's track, or run
  through the antenna keep-out -- otherwise it leaves the connection as
  ratsnest rather than fake a route. Current numbers (regenerate with
  `check.sh` to reconfirm): **20 of 65 point-to-point hops routed**, 3 of
  25 signal/power nets fully routed, 6 partially, 16 left entirely as
  ratsnest (46 unconnected items in the DRC report). GND is handled
  entirely by copper pour instead of discrete traces, which is normal
  practice, not a routing gap. **Finishing routing by hand in the KiCad
  GUI is the single biggest next step before this is fab-ready.**
- **Board is 70x55mm, not the spec's <=60x45mm target.** This is a
  direct, documented consequence of a library gap, not a claim that the
  real board can't hit spec -- see the MCU footprint note below.
- **No thermal analysis.** Nothing has been checked for the AMS1117's
  dropout/dissipation under sustained WiFi TX bursts, copper pour
  thermal relief, or enclosure thermal behavior.
- **No real DFM/panelization review**, no impedance analysis on the USB
  differential pair, no BOM stock/lead-time check beyond LCSC part-number
  estimates.
- **1 cosmetic courtyard overlap and 2 cosmetic silkscreen nags** remain
  in DRC, as noted above -- neither is electrical.

## The MCU footprint substitution -- read this before opening the board

The spec calls for an **ESP32-C3-MINI-1** module. KiCad 10's stock
libraries do not ship a MINI-1 symbol or footprint (they have
ESP32-C3-WROOM-02, ESP32-C3-DevKitM-1, and ESP32-C6-MINI-1, but not
C3-MINI-1). This design uses **RF_Module:ESP32-C3-WROOM-02** as a
stand-in everywhere U1 appears:

- Same ESP32-C3 SoC, same GPIO numbering and strapping behavior
  (GPIO0-10, 18/19 USB, 20/21 UART0) -- every net connection and the GPIO
  table below are electrically representative of the real MINI-1.
- The WROOM-02 footprint is physically **larger** (~18.2x20.2mm) than the
  real MINI-1 (~15.4x20.5mm) and its castellated pad positions do not
  match MINI-1's datasheet pad map. That size difference is the reason
  this board is 70x55mm instead of the spec's 60x45mm target, and the
  antenna keep-out zone in `build_board.py` is sized against the
  WROOM-02's geometry, not MINI-1's.

**Before fabrication, EE review must swap in a real ESP32-C3-MINI-1
footprint** (built from Espressif's datasheet pad map) and re-verify the
antenna keep-out against MINI-1's actual RF section location. Doing that
should let the board shrink back toward the 60x45mm target.

## GPIO assignment (authoritative)

| GPIO | Net | Function | Notes |
|---|---|---|---|
| GPIO0 | `CT_SIG` | ADC1_CH0, CT current sense | through anti-alias RC + bias network |
| GPIO1 | `ONEWIRE` | DS18B20 bus (both JST-XH chains, shared) | single 4.7k pull-up |
| GPIO2 | -- | **reserved, unpopulated** | strapping pin; no load at boot |
| GPIO3 | `DRIP_SIG` | drip-counter pulse in | RC debounced |
| GPIO4 | `LED_STATUS_A` | status LED (green) | ADC1_CH4 unused as analog |
| GPIO5 | `LED_ALERT_A` | alert LED (red) | |
| GPIO6 | `I2C_SCL` | Qwiic expansion | |
| GPIO7 | `I2C_SDA` | Qwiic expansion | |
| GPIO8 | -- | **reserved, unpopulated** | strapping pin; no load at boot |
| GPIO9 | `BTN_BOOT` | BOOT button | conventional strap-to-GND use |
| GPIO10 | `BTN_ACK` | user acknowledge button | |
| GPIO18 | `USB_DM` | native USB D- | fixed function |
| GPIO19 | `USB_DP` | native USB D+ | fixed function |
| GPIO20 | `UART_RX` | debug header | |
| GPIO21 | `UART_TX` | debug header | |
| EN | `EN_RESET` | RESET button (EN-to-GND) | 10k pull-up + 100nF per Espressif ref design |

GPIO2 and GPIO8 -- the two strapping pins other than BOOT/GPIO9 -- are
left completely unpopulated: no resistor, no connector, nothing that
could present a load at boot, per the board spec.

## Design-for-compliance notes

- **SELV only.** Everything on this board runs at 5V or below; mains
  never touches it. USB-C is configured 5V-only via 5.1k CC pulldowns,
  no PD negotiation.
- **Pre-certified module, no custom antenna.** The MCU's onboard PCB
  antenna is used as-is; this design does not attempt a custom antenna,
  which is what keeps the module's existing FCC modular approval valid.
- **ESD protection on every user-touchable connector path**: USBLC6-2
  class protection on USB VBUS/D+/D-; a BAT54S dual-Schottky clamp on the
  CT sense line.
- **No exposed copper test points near the board edge mounting area.**
  Both M3 mounting holes use the `MountingHole_3.2mm_M3` footprint, which
  is a bare drilled hole with no copper pad.

## Repo map

| File | What it is |
|---|---|
| `schematic.py` | SKiDL design-as-code schematic. Run it to regenerate `guard.net`. Heavily commented -- read this first, it's the reviewable schematic. |
| `guard.net` | Generated KiCad netlist (do not hand-edit; regenerate from `schematic.py`). |
| `build_board.py` | pcbnew layout script: placement, ground pours, antenna keep-out, scripted routing. Fully re-runnable -- regenerates `guard.kicad_pcb` from scratch every time. |
| `guard.kicad_pcb` / `.kicad_pro` / `.kicad_prl` | Generated PCB + project files. Open `guard.kicad_pcb` (or the `.kicad_pro`) in KiCad's PCB Editor to inspect/hand-route. |
| `check.sh` | The verification gate: schematic ERC -> board build -> DRC -> renders, in order, with a real non-zero exit on an electrical problem. |
| `drc_report.json` | Latest `kicad-cli pcb drc` output (regenerated by `check.sh`). |
| `bom.csv` | Bill of materials with LCSC estimates and a cost rollup. |
| `renders/` | `top.png` / `bottom.png` (3D-style renders) and `top.svg` / `bottom.svg` (flat copper+silk+edge views), regenerated by `check.sh`. |

## How to run `check.sh`

You need:

1. **KiCad 10** with `kicad-cli` on `PATH`, and its bundled `pcbnew`
   Python module importable from a system `python3` (verify with
   `python3 -c "import pcbnew"`).
2. A separate Python environment with **SKiDL** installed, pointed at
   KiCad's symbol libraries:

   ```
   python3 -m venv pcb/guard/venv   # or wherever you keep it
   source pcb/guard/venv/bin/activate
   pip install skidl
   ```

   SKiDL and `pcbnew` have never needed to coexist in one interpreter
   for this project -- `schematic.py` runs under the SKiDL venv,
   `build_board.py` runs under the system `python3` that has `pcbnew`.
   `schematic.py` itself hard-codes `KICAD_SYMBOL_DIR` (defaulting to
   `/usr/share/kicad/symbols`) so it doesn't depend on shell env vars.

3. Then, from `pcb/guard/`:

   ```
   ./check.sh
   ```

   `check.sh` looks for a SKiDL-capable interpreter at `./venv/bin/python3`
   first, then falls back to whatever's on `PATH`; override with
   `SKIDL_PYTHON=/path/to/python3`. It looks for `pcbnew` on plain
   `python3` by default; override with `PCBNEW_PYTHON=/path/to/python3`
   if yours lives somewhere else.

## How to open this in the KiCad GUI

- **PCB only:** open `guard.kicad_pcb` (or `guard.kicad_pro`) directly in
  KiCad's PCB Editor. Placement, pours, the antenna keep-out zone, and
  whatever the scripted router routed are all there to inspect, and it's
  a normal KiCad board file -- hand-routing the rest, nudging placement,
  and rerunning DRC all work exactly like any other KiCad project.
- **No `.kicad_sch` exists.** The schematic is `schematic.py` itself (the
  SKiDL source) plus the generated `guard.net` netlist -- there's no
  KiCad schematic file to open in the Schematic Editor. If a real KiCad
  schematic sheet becomes useful later (e.g. so a human can redline it
  directly), generating one from `guard.net` is a reasonable next step,
  not something this experiment did.

## Next steps

1. **Professional EE review** (this board's one paid hour) -- start with
   this README's limitations list and the MCU footprint-substitution
   note above.
2. **Swap in a real ESP32-C3-MINI-1 footprint** built from Espressif's
   datasheet pad map, re-verify the antenna keep-out against it, and see
   how close the board comes back to the 60x45mm target.
3. **Finish routing.** 20 of 65 hops are routed; the rest need either a
   smarter scripted router or hand-routing in the KiCad GUI.
4. **JLCPCB DFM upload** once routing is complete and the footprint swap
   above is done -- their DFM checker will catch fab-specific issues
   (soldermask, silkscreen-on-pad, panelization) that a generic DRC run
   doesn't.
