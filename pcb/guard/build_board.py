#!/usr/bin/env python3
"""
FrostSight Guard rev A (draft) -- PCB layout script.

Reads pcb/guard/guard.net (written by schematic.py), builds a fresh
guard.kicad_pcb from scratch every time it runs (safe to re-run -- it does
not try to preserve hand-edits made in the KiCad GUI), places every
footprint at a deliberate, documented location, pours ground copper on
both layers, and attempts scripted routing of short, unambiguous
connections. Whatever it can't route with a simple heuristic is left as
ratsnest -- see the routing summary this script prints (and check.sh's
log) for the honest unrouted count.

Requires KiCad's `pcbnew` Python module -- this repo's environment has it
in the *system* python3 (not the SKiDL venv), see pcb/guard/README.md.

Run directly:

    python3 build_board.py
"""

import datetime
import os
import re
import sys

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
NETLIST_PATH = os.path.join(HERE, "guard.net")
BOARD_PATH = os.path.join(HERE, "guard.kicad_pcb")
FOOTPRINT_ROOT = "/usr/share/kicad/footprints"

# The board spec's target is <=60x45mm. This build comes in at 70x55mm --
# see the MCU footprint-substitution note in schematic.py: the stock
# RF_Module:ESP32-C3-WROOM-02 footprint used as a stand-in for the real
# ESP32-C3-MINI-1 is physically larger (~18.2x20.2mm vs MINI-1's real
# ~15.4x20.5mm) and needs more clearance around it than a real MINI-1
# would, so this placeholder-footprint build is oversized versus the
# spec's target. That is a consequence of the library substitution, not
# a claim that the real board can't hit 60x45mm -- flagged again in the
# README's limitations section.
BOARD_W = 70.0
BOARD_H = 55.0

MM = pcbnew.FromMM  # shorthand: mm -> internal units


# =======================================================================
# Minimal S-expression parser -- just enough to walk the KiCad netlist
# format SKiDL's generate_netlist() writes. Robust to the exact
# whitespace layout because it tokenizes rather than relying on regex
# line-matching.
# =======================================================================
def parse_sexp(text):
    tokens = re.findall(r'\(|\)|"[^"]*"|[^\s()]+', text)
    pos = 0

    def parse():
        nonlocal pos
        assert tokens[pos] == "("
        pos += 1
        lst = []
        while tokens[pos] != ")":
            if tokens[pos] == "(":
                lst.append(parse())
            else:
                tok = tokens[pos]
                if tok.startswith('"'):
                    tok = tok[1:-1]
                lst.append(tok)
                pos += 1
        pos += 1
        return lst

    return parse()


def get(lst, tag):
    """First direct child of `lst` that is itself a list tagged `tag`."""
    for item in lst:
        if isinstance(item, list) and item and item[0] == tag:
            return item
    return None


def get_all(lst, tag):
    return [item for item in lst if isinstance(item, list) and item and item[0] == tag]


def field_str(lst, tag):
    node = get(lst, tag)
    if node is None:
        return None
    # A field node looks like ['ref', 'C1'] -- the value is everything
    # after the tag, usually a single string.
    return node[1] if len(node) > 1 else ""


def load_netlist(path):
    with open(path) as f:
        text = f.read()
    tree = parse_sexp(text)

    comps = {}
    comps_section = get(tree, "components")
    for comp in get_all(comps_section, "comp"):
        ref = field_str(comp, "ref")
        comps[ref] = {
            "value": field_str(comp, "value") or "",
            "footprint": field_str(comp, "footprint") or "",
        }

    # pad_net[(ref, pin)] = net_name
    pad_net = {}
    net_nodes = {}  # net_name -> [(ref, pin), ...]
    nets_section = get(tree, "nets")
    for net in get_all(nets_section, "net"):
        name = field_str(net, "name")
        nodes = []
        for node in get_all(net, "node"):
            ref = field_str(node, "ref")
            pin = field_str(node, "pin")
            pad_net[(ref, pin)] = name
            nodes.append((ref, pin))
        net_nodes[name] = nodes

    return comps, pad_net, net_nodes


# =======================================================================
# Footprint-vs-schematic pin-numbering overrides.
#
# SKiDL/KiCad normally connect a symbol pin to a footprint pad by matching
# the pin NUMBER to the pad NUMBER as strings, and for every part in this
# design that works automatically (R/C/LED/switches/BAT54S/AMS1117's 3
# leads/USB-C/USBLC6/JST & pin headers/the MCU all use numeric pin<->pad
# numbers that line up). Two parts don't, and are called out here rather
# than silently mismatched:
#
#  - J2 (3.5mm TRS jack): the AudioJack3 symbol's ring pin is number "R",
#    but the real PJ320D footprint has two ring-related pads, "R1" and
#    "R2" (R1 = ring contact, R2 = the jack's normally-closed detection
#    tab -- unused in this design), plus two unnamed mechanical/shield
#    mounting pads. Map "R" -> "R1" (tied to GND like the sleeve), leave
#    "R2" and the two mounting pads NC-but-grounded (jack shell ground).
#  - U3 (AMS1117-3.3, SOT-223): the symbol only exposes 3 leads
#    (GND/VO/VI), but the SOT-223 footprint has a 4th pad for the
#    package's metal tab. For a 3-terminal SOT-223 regulator the tab is
#    electrically the output pin -- tie pad "4" to whatever net pin "2"
#    (VO) landed on.
# =======================================================================
PAD_OVERRIDES = {
    ("J2", "R1"): ("J2", "R"),
    ("J2", "R2"): None,  # explicitly NC (detect-switch tab, unused)
    ("J2", ""): "GND",  # both unnamed mechanical/shield pads -> chassis GND
}
TAB_TIE = {
    ("U3", "4"): ("U3", "2"),
}


# =======================================================================
# Placement table: ref -> (x_mm, y_mm, rotation_deg)
#
# Layout zones on the 60x45mm board (see README.md for the picture in
# words and the render images for the picture in pixels):
#
#   Top-center   (x 15-45, y 0-8)   MCU antenna keep-out strip
#   Top-left     (x 0-17,  y 0-20)  USB-C in, ESD, 3V3 regulator
#   Top-right    (x 45-60, y 0-19)  UI: status/alert LEDs, ack/boot/reset
#   Right edge   (x 48-60, y 20-40) Expansion: I2C (Qwiic), UART debug
#   Bottom-left  (x 3-20,  y 24-43) CT analog front end (away from USB)
#   Bottom edge  (x 20-58, y 36-44) DS18B20 x2 + drip counter JST headers
#
# Everything here is a first-pass placement produced by this script, then
# corrected after inspecting pcb/guard/renders/*.png -- see the README's
# "what's not done" section for what the second inspection pass fixed.
# =======================================================================
PLACEMENT = {
    # --- MCU -----------------------------------------------------------
    "U1": (35.0, 15.0, 0),  # antenna end (local -Y) lands at the top edge;
    # pads start at abs y=9 (local -6), body top edge at abs y=1.79
    "R1": (23.0, 10.0, 0),  # EN pull-up, left of MCU, clear of keep-out
    "C1": (23.0, 14.0, 0),  # EN cap
    "C2": (48.0, 10.0, 0),  # MCU bulk decoupling, right of MCU
    "C3": (48.0, 14.0, 0),  # MCU HF decoupling
    # --- Power in / USB-C (top-left) -----------------------------------
    # U3 (SOT-223) is the physically biggest part in this cluster once
    # its tab pad is counted -- 8.3x6.1mm overall, not the ~7x4mm a SOT-223
    # "typically" runs -- so it and everything within ~5mm of it got
    # extra breathing room after the first DRC pass found real copper
    # overlaps here (not just tight-but-legal spacing).
    "J1": (4.0, 10.0, 270),  # USB-C receptacle, mates toward -X (left edge);
    # shifted 2mm left of the first-pass placement after the render
    # inspection showed its mating face sitting ~2mm inboard of the
    # board edge instead of flush with/overhanging it (pads stay safely
    # on-board: connector pad row lands at abs x~8, still >4mm from
    # U2/R4/R5)
    "U2": (16.0, 6.0, 0),  # USBLC6-2SC6 ESD, right next to the connector
    "R4": (14.0, 10.0, 0),  # 22R series, D+, between ESD and MCU
    "R5": (18.0, 10.0, 0),  # 22R series, D-
    "R2": (5.0, 18.0, 0),  # CC1 5.1k pulldown
    "R3": (9.0, 18.0, 0),  # CC2 5.1k pulldown
    "C4": (13.0, 18.0, 0),  # VBUS bulk cap, at the connector
    "C5": (17.0, 18.0, 0),  # VBUS HF cap
    "U3": (10.0, 27.0, 0),  # AMS1117-3.3, downstream of VBUS caps
    "C6": (2.0, 27.0, 0),  # regulator input cap
    "C7": (18.0, 27.0, 0),  # regulator output cap
    "C8": (18.0, 31.0, 0),  # regulator output HF cap
    # --- UI (top-right) --------------------------------------------------
    "D2": (55.0, 4.0, 0),  # status LED (green)
    "R12": (55.0, 8.0, 0),
    "D3": (61.0, 4.0, 0),  # alert LED (red)
    "R13": (61.0, 8.0, 0),
    "SW1": (54.0, 16.0, 0),  # ack button
    "SW2": (64.0, 16.0, 0),  # BOOT button -- >=9mm from SW1/SW3 so their
    "SW3": (59.0, 25.0, 0),  # RESET button   built-in keep-out zones clear
    # --- Expansion (right edge) ------------------------------------------
    "J6": (65.0, 33.0, 0),  # I2C / Qwiic, JST-SH 4p
    "R14": (57.0, 33.0, 0),  # SCL pull-up
    "R15": (57.0, 37.0, 0),  # SDA pull-up
    "J7": (64.0, 45.0, 0),  # UART debug header
    # --- CT analog front end (bottom-left, away from USB/switching) ------
    # J2's horizontal-jack footprint reaches ~5mm past its own pads toward
    # -X (the barrel), so everything else in this zone is kept at x>=13
    # to stay clear of it, and this whole zone is confined to x<20 so it
    # can't collide with the JST/temp/drip row (x>=28, see below) no
    # matter how each rotated connector's exact courtyard works out.
    "J2": (7.0, 44.0, 0),  # 3.5mm TRS, mates toward -X (left edge)
    "R6": (17.0, 34.0, 0),  # bias divider, 3V3 side
    "R7": (17.0, 37.0, 0),  # bias divider, GND side
    "C9": (13.0, 34.0, 0),  # bias node decoupling
    "C10": (13.0, 37.0, 0),  # AC coupling cap
    "R8": (17.0, 40.0, 0),  # anti-alias series R
    "C11": (22.0, 40.0, 0),  # anti-alias shunt C -- pulled clear of J2's
    # courtyard (x up to ~13.1mm at J2's placement), which the first DRC
    # pass showed genuinely overlapping the original (13, 40) spot
    "D1": (17.0, 44.0, 0),  # BAT54S clamp
    # --- Temperature + drip (bottom edge) ---------------------------------
    # Each JST-XH header is rotated 90 deg, which turns its 2.5mm-pitch
    # pin row into a ~7.5mm-tall vertical column running from the
    # placement point upward (toward smaller Y); columns are spaced
    # 14mm apart so neighboring connector bodies can't touch, and each
    # header's own pull-up/debounce parts sit above the column, clear of
    # it in Y as well as clear of the CT zone in X (x>=28 here vs <20
    # there).
    "J3": (30.0, 52.0, 90),  # DS18B20 chain 1
    "R9": (30.0, 40.0, 0),  # shared 1-Wire pull-up
    "J4": (44.0, 52.0, 90),  # DS18B20 chain 2
    "J5": (58.0, 52.0, 90),  # drip counter
    "R10": (50.0, 40.0, 0),  # drip pull-down
    "R11": (53.0, 40.0, 0),  # drip series R
    "C12": (56.0, 40.0, 0),  # drip debounce C
}

# Two M3 mounting holes -- corners clear of connectors/keep-out.
# Computed, not eyeballed: for each candidate point, the clearance to
# every OTHER footprint's bounding box was checked programmatically
# (scripted-placement sweep, kept out of this file for brevity) after
# earlier hand-picked spots kept landing on top of something in this
# densely packed layout. (23, 27) is the most open spot on the whole
# board (3.0mm to the nearest neighboring footprint box) and it *still*
# leaves a courtyard-overlap DRC nag against C7, because the
# MountingHole_3.2mm_M3 footprint's own assembly-exclusion courtyard is
# a 3.45mm-radius circle -- bigger than the clearance this board has
# anywhere to give it. That single courtyard_overlap (not a copper/
# electrical violation) is accepted and documented in the README rather
# than chased further; see check.sh's DRC summary.
MOUNTING_HOLES = [(23.0, 27.0), (4.0, 35.0)]

# Antenna keep-out: no copper (pour, track, or via) on either layer in
# this strip. It covers the MCU's antenna-end body (local Y -13.21..~-6
# once placed at U1's position/rotation above) plus margin toward the
# board edge -- see schematic.py's MCU footprint-substitution note for
# why this is a conservative approximation rather than a datasheet-exact
# keep-out for the real ESP32-C3-MINI-1.
KEEPOUT_RECT_MM = (20.0, 0.0, 50.0, 8.0)  # x0, y0, x1, y1 -- stops just
# short of the MCU's pad row (abs y=9 at this placement) so the MCU's own
# functional pads are not inside their own keep-out.

# Nets handled by copper pour instead of discrete traces.
POUR_NETS = ["GND"]

# Per-net track width in mm for the scripted router.
POWER_NETS = {"VBUS", "+3V3", "CC1", "CC2", "EN_RESET"}
TRACK_WIDTH_SIGNAL_MM = 0.30
TRACK_WIDTH_POWER_MM = 0.45

# A routed hop longer than this is left as ratsnest instead -- "short,
# obvious connections" per the brief, not a full autorouter.
MAX_ROUTE_HOP_MM = 24.0


def footprint_lib_path(fp_string):
    nickname, name = fp_string.split(":", 1)
    return os.path.join(FOOTPRINT_ROOT, f"{nickname}.pretty"), name


def build():
    comps, pad_net, net_nodes = load_netlist(NETLIST_PATH)
    print(f"Loaded netlist: {len(comps)} components, {len(net_nodes)} nets")

    board = pcbnew.CreateEmptyBoard()

    # The RF_Module:ESP32-C3-WROOM-02 footprint's GND pad ("19") includes
    # a small thermal-via pattern drilled at 0.2mm, per the stock KiCad
    # library -- below the board's stock default minimum through-hole
    # drill of 0.3mm. 0.2mm is within JLCPCB's standard capability, so
    # this relaxes the design rule to match the library part rather than
    # alter the part's own footprint.
    ds = board.GetDesignSettings()
    ds.m_MinThroughDrill = MM(0.2)

    # ---- Board outline (Edge.Cuts rectangle) --------------------------
    outline = pcbnew.PCB_SHAPE(board)
    outline.SetShape(pcbnew.SHAPE_T_RECTANGLE)
    outline.SetStart(pcbnew.VECTOR2I(MM(0), MM(0)))
    outline.SetEnd(pcbnew.VECTOR2I(MM(BOARD_W), MM(BOARD_H)))
    outline.SetLayer(pcbnew.Edge_Cuts)
    outline.SetWidth(MM(0.15))
    board.Add(outline)

    # ---- Silkscreen title text -----------------------------------------
    # This board is packed tightly enough (43 parts on 70x55mm) that
    # there is no fully open corridor left for a long title string --
    # (40, 26.5) is the most open spot a boundingbox sweep against every
    # other footprint found for an ~8mm-wide label, so the label itself
    # is kept short (compact YYMMDD date) to fit it.
    title = pcbnew.PCB_TEXT(board)
    today = datetime.date.today().strftime("%y%m%d")
    title.SetText(f"GUARD A {today}")
    title.SetPosition(pcbnew.VECTOR2I(MM(40), MM(26.5)))
    title.SetLayer(pcbnew.F_SilkS)
    # 0.8mm is KiCad's default minimum legible silkscreen text height --
    # a smaller size cleared placement more easily but failed DRC's
    # text_height check, so the message stays this short instead.
    title.SetTextSize(pcbnew.VECTOR2I(MM(0.8), MM(0.8)))
    title.SetTextThickness(MM(0.12))
    title.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_CENTER)
    board.Add(title)

    # ---- Net table ------------------------------------------------------
    netinfo = {}
    for name in net_nodes:
        if not name:
            continue
        ni = pcbnew.NETINFO_ITEM(board, name)
        board.Add(ni)
        netinfo[name] = ni

    def net_for(ref, pin):
        key = (ref, pin)
        if key in PAD_OVERRIDES:
            mapped = PAD_OVERRIDES[key]
            if mapped is None:
                return None
            if isinstance(mapped, str):
                return mapped
            ref, pin = mapped
            key = (ref, pin)
        return pad_net.get(key)

    # ---- Place footprints ------------------------------------------------
    footprints = {}
    missing_placement = []
    for ref, info in comps.items():
        if ref not in PLACEMENT:
            missing_placement.append(ref)
            continue
        x_mm, y_mm, rot = PLACEMENT[ref]
        lib_path, fp_name = footprint_lib_path(info["footprint"])
        fp = pcbnew.FootprintLoad(lib_path, fp_name)
        if fp is None:
            raise RuntimeError(f"Could not load footprint {info['footprint']} for {ref}")
        fp.SetReference(ref)
        fp.SetValue(info["value"])
        fp.SetPosition(pcbnew.VECTOR2I(MM(x_mm), MM(y_mm)))
        fp.SetOrientationDegrees(rot)
        board.Add(fp)
        footprints[ref] = fp

        # Assign nets to every physical pad matching each logical pad
        # number (handles multi-pad logical pins like the MCU's split
        # thermal/GND pad or the tactile switches' doubled contacts).
        pad_numbers = {p.GetPadName() for p in fp.Pads()}
        for padnum in pad_numbers:
            net_name = net_for(ref, padnum)
            # The SOT-223 tab (pad "4" on U3) has no symbol pin of its
            # own -- tie it to whatever net pin "2" landed on.
            if net_name is None and (ref, padnum) in TAB_TIE:
                tie_ref, tie_pin = TAB_TIE[(ref, padnum)]
                net_name = pad_net.get((tie_ref, tie_pin))
            if net_name is None:
                continue  # genuinely NC (e.g. J2/R2, J5 spare pin)
            ni = netinfo.get(net_name)
            if ni is None:
                continue
            for pad in fp.Pads():
                if pad.GetPadName() == padnum:
                    pad.SetNet(ni)

    if missing_placement:
        print(f"WARNING: no placement coordinates for: {missing_placement}")

    # ---- Mounting holes ---------------------------------------------------
    mh_lib = os.path.join(FOOTPRINT_ROOT, "MountingHole.pretty")
    for i, (x_mm, y_mm) in enumerate(MOUNTING_HOLES, start=1):
        fp = pcbnew.FootprintLoad(mh_lib, "MountingHole_3.2mm_M3")
        fp.SetReference(f"MH{i}")
        fp.SetPosition(pcbnew.VECTOR2I(MM(x_mm), MM(y_mm)))
        board.Add(fp)

    # ---- Antenna keep-out (rule area, both copper layers) ------------------
    x0, y0, x1, y1 = KEEPOUT_RECT_MM
    keepout = pcbnew.ZONE(board)
    keepout.SetIsRuleArea(True)
    keepout.SetDoNotAllowTracks(True)
    keepout.SetDoNotAllowVias(True)
    keepout.SetDoNotAllowZoneFills(True)
    keepout.SetDoNotAllowFootprints(False)  # the MCU module itself lives here
    keepout_layers = pcbnew.LSET()
    keepout_layers.AddLayer(pcbnew.F_Cu)
    keepout_layers.AddLayer(pcbnew.B_Cu)
    keepout.SetLayerSet(keepout_layers)
    poly = keepout.Outline()
    poly.NewOutline()
    for x, y in [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]:
        poly.Append(MM(x), MM(y))
    board.Add(keepout)

    # ---- Ground pour, both layers -----------------------------------------
    gnd = netinfo["GND"]
    for layer in (pcbnew.F_Cu, pcbnew.B_Cu):
        zone = pcbnew.ZONE(board)
        zone.SetLayer(layer)
        zone.SetNet(gnd)
        zone.SetZoneName(f"GND_POUR_{'TOP' if layer == pcbnew.F_Cu else 'BOTTOM'}")
        zone.SetMinThickness(MM(0.15))
        # Keep the pour clearly separated from every non-GND pad/track --
        # the default 0mm zone clearance is what caused GND to short
        # against VBUS/+3V3/signal nets on the first pass of this layout.
        zone.SetLocalClearance(MM(0.30))
        # Solid (not thermal-relief) pad connection -- with several pads
        # (e.g. J1's shield/GND pads) only bordering the pour on one
        # side, the default thermal-relief spokes came up short of
        # KiCad's minimum spoke count. Solid fill is a fine trade for a
        # small, JLCPCB-assembled board like this one.
        zone.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
        poly = zone.Outline()
        poly.NewOutline()
        m = 1.0  # inset from board edge, mm
        for x, y in [(m, m), (BOARD_W - m, m), (BOARD_W - m, BOARD_H - m), (m, BOARD_H - m)]:
            poly.Append(MM(x), MM(y))
        board.Add(zone)

    # ---- Scripted routing: short, unambiguous hops only --------------------
    routed_hops = 0
    total_hops = 0
    fully_routed_nets = 0
    partially_routed_nets = []
    unrouted_nets = []
    placed_segments = []  # [(net_name, (x1,y1), (x2,y2)), ...] for crossing checks

    def pad_center_mm(ref, padnum):
        fp = footprints.get(ref)
        if fp is None:
            return None
        for pad in fp.Pads():
            if pad.GetPadName() == padnum:
                pos = pad.GetPosition()
                return (pcbnew.ToMM(pos.x), pcbnew.ToMM(pos.y))
        return None

    def _ccw(a, b, c):
        return (c[1] - a[1]) * (b[0] - a[0]) > (b[1] - a[1]) * (c[0] - a[0])

    def segments_intersect(p1, p2, p3, p4):
        return _ccw(p1, p3, p4) != _ccw(p2, p3, p4) and _ccw(p1, p2, p3) != _ccw(p1, p2, p4)

    def segment_hits_keepout(p1, p2):
        x0, y0, x1, y1 = KEEPOUT_RECT_MM
        pad_ = 0.2  # small margin, mm
        x0, y0, x1, y1 = x0 - pad_, y0 - pad_, x1 + pad_, y1 + pad_
        corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
        # Cheap conservative check: either endpoint inside the rect, or
        # the segment crosses one of the rect's four edges.
        for p in (p1, p2):
            if x0 <= p[0] <= x1 and y0 <= p[1] <= y1:
                return True
        for a, b in zip(corners, corners[1:] + corners[:1]):
            if segments_intersect(p1, p2, a, b):
                return True
        return False

    def segment_crosses_other_net(p1, p2, this_net):
        for other_net, q1, q2 in placed_segments:
            if other_net == this_net:
                continue
            if segments_intersect(p1, p2, q1, q2):
                return True
        return False

    def _point_seg_dist(p, a, b):
        ax, ay = a
        bx, by = b
        px, py = p
        dx, dy = bx - ax, by - ay
        seg_len2 = dx * dx + dy * dy
        if seg_len2 == 0:
            t = 0.0
        else:
            t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / seg_len2))
        cx, cy = ax + t * dx, ay + t * dy
        return ((px - cx) ** 2 + (py - cy) ** 2) ** 0.5

    # Every placed pad's (net, x, y), gathered once so a candidate track
    # segment can be checked against pads it would run past -- a straight
    # nearest-neighbor hop between two same-net pads can easily clip a
    # third, unrelated pad sitting in between on a tightly packed board.
    all_pads_mm = []
    for ref, fp in footprints.items():
        for pad in fp.Pads():
            pos = pad.GetPosition()
            all_pads_mm.append(
                (pad.GetNetname(), pcbnew.ToMM(pos.x), pcbnew.ToMM(pos.y))
            )

    PAD_CLEARANCE_MM = 1.1  # conservative half-pad-plus-clearance radius --
    # sized to also catch fine-pitch (1mm) JST-SH pads, not just 0603/0805

    def segment_hits_foreign_pad(p1, p2, this_net):
        for net_name, px, py in all_pads_mm:
            if net_name == this_net or not net_name:
                continue
            if _point_seg_dist((px, py), p1, p2) < PAD_CLEARANCE_MM:
                return True
        return False

    for net_name, nodes in net_nodes.items():
        if not net_name or net_name in POUR_NETS:
            continue
        positions = []
        for ref, pin in nodes:
            p = pad_center_mm(ref, pin)
            if p is not None:
                positions.append(p)
        if len(positions) < 2:
            continue

        # Greedy nearest-neighbor chain through this net's pads.
        remaining = positions[:]
        path = [remaining.pop(0)]
        while remaining:
            last = path[-1]
            remaining.sort(key=lambda p: (p[0] - last[0]) ** 2 + (p[1] - last[1]) ** 2)
            path.append(remaining.pop(0))

        width = MM(TRACK_WIDTH_POWER_MM if net_name in POWER_NETS else TRACK_WIDTH_SIGNAL_MM)
        hops_here = len(path) - 1
        routed_here = 0
        total_hops += hops_here
        for (x1p, y1p), (x2p, y2p) in zip(path, path[1:]):
            p1, p2 = (x1p, y1p), (x2p, y2p)
            dist = ((x1p - x2p) ** 2 + (y1p - y2p) ** 2) ** 0.5
            if dist > MAX_ROUTE_HOP_MM:
                continue  # too far for a "short, obvious" scripted hop
            if segment_hits_keepout(p1, p2):
                continue  # would route through the antenna keep-out
            if segment_crosses_other_net(p1, p2, net_name):
                continue  # would short against an already-routed net
            if segment_hits_foreign_pad(p1, p2, net_name):
                continue  # would clip a pad that isn't on this net
            track = pcbnew.PCB_TRACK(board)
            track.SetStart(pcbnew.VECTOR2I(MM(x1p), MM(y1p)))
            track.SetEnd(pcbnew.VECTOR2I(MM(x2p), MM(y2p)))
            track.SetWidth(width)
            track.SetLayer(pcbnew.F_Cu)
            track.SetNet(netinfo[net_name])
            board.Add(track)
            placed_segments.append((net_name, p1, p2))
            routed_here += 1
        routed_hops += routed_here
        if routed_here == hops_here:
            fully_routed_nets += 1
        elif routed_here > 0:
            partially_routed_nets.append(net_name)
        else:
            unrouted_nets.append(net_name)

    total_nets = len([n for n in net_nodes if n and n not in POUR_NETS])
    print("=" * 70)
    print("Routing summary (scripted short-hop router, GND handled by pour):")
    print(f"  Nets considered for tracing: {total_nets} (GND excluded, uses copper pour)")
    print(f"  Fully routed:     {fully_routed_nets}")
    print(f"  Partially routed: {len(partially_routed_nets)} {partially_routed_nets}")
    print(f"  Not routed at all (pure ratsnest): {len(unrouted_nets)} {unrouted_nets}")
    print(f"  Hops routed: {routed_hops} / {total_hops} total point-to-point hops")
    print("=" * 70)

    # ---- Fill zones ---------------------------------------------------------
    filler = pcbnew.ZONE_FILLER(board)
    filler.Fill(board.Zones())

    board.Save(BOARD_PATH)
    print(f"Wrote {BOARD_PATH}")

    return {
        "total_nets": total_nets,
        "fully_routed_nets": fully_routed_nets,
        "partially_routed_nets": partially_routed_nets,
        "unrouted_nets": unrouted_nets,
        "routed_hops": routed_hops,
        "total_hops": total_hops,
    }


if __name__ == "__main__":
    if not os.path.exists(NETLIST_PATH):
        print(f"ERROR: {NETLIST_PATH} not found -- run schematic.py first.", file=sys.stderr)
        sys.exit(1)
    build()
