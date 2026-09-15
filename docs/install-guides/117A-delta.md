# Install guide — Frosty Factory 117A (delta from 137A)

> **PROVISIONAL — re-verify against the 117A service manual during the
> first install.** Source:
> [rf_service_man._117_new_2016.pdf](https://www.frostyfactory.com/downloads/rf_service_man._117_new_2016.pdf).
> This document has not yet been checked against a physical 117A or that
> manual in detail; treat every part number and placement note below as a
> starting point, not a confirmed fact, until the first field install closes
> the loop. Update this banner and the notes below once that's done.

This is a **delta** document. Follow [137A.md](137A.md) as the base
procedure, including its safety gate, panel-removal order, and CT/opto/probe
placement logic — only the differences below apply. Read
[../safety.md](../safety.md) first regardless.

## What's different on the 117A

| Aspect | 137A (base) | 117A |
|---|---|---|
| Cabinet size | larger | ~25"H × 11"W × 21"D |
| Hopper / cylinder capacity | — | 12 qt hopper / 3.5 qt cylinder |
| TCC sensing element | Microswitch F0346 | Reportedly a **mercury switch (F0752)** instead — re-verify on-site |
| Drive | Belt-driven Franklin motor, direct | Belt Franklin-type **with gearbox F5125** |
| Panel part numbers | 137A-specific | Differ — do not assume 137A panel fastener/part numbers apply |

## What stays the same

- CT clamp placement logic (one conductor per clamp, beater leg + compressor
  leg) — same approach, confirm exact junction-box layout on-site since the
  smaller cabinet may put the junction box in a different position.
- Temperature-probe placement logic (cylinder jacket, condenser air-in,
  condenser air-out, ambient, discharge-line thermocouple) — same targets,
  same reasoning, positions confirmed on-site given the smaller cabinet.
- The 24V control-chain tap points remain valid in principle: same
  contactor (F0478), same HP switch (F0661), same transformer (F4995).
- The leak-sensing kit (drip-tube drop counter, plus the optional moisture
  pad / gas sensor add-ons) installs identically — confirm the drip tube's
  exact location on this cabinet on-site before clipping the drop counter
  on.

## What needs on-site judgment

> **WARNING:** All notes below assume the machine is unplugged and locked
> out per [../safety.md](../safety.md), same as the 137A procedure.

1. **TCC-node tap behavior may differ.** If the 117A genuinely uses a
   mercury switch (F0752) rather than microswitch F0346 for torque/TCC
   sensing, the electrical behavior at that node (contact bounce, switching
   characteristics, orientation-sensitivity of a mercury switch) may not
   match the 137A's microswitch assumptions baked into the optional opto-3
   tap in [137A.md § 4](137A.md#4-ac-presence-taps). Treat opto-3 on a 117A
   as **experimental** until confirmed against the service manual and a
   bench check of the actual switch behavior. The required opto-1 (beater
   leg) and opto-2 (contactor coil) taps are unaffected — those nodes are
   the same as 137A.
2. **Pod-A (beater drive) mounting spot must be chosen on-site.** The
   137A guide anchors Pod A near the flywheel at the upper rear, driven by
   a direct belt/flywheel arrangement. The 117A drive includes a gearbox
   (F5125) in that path, which changes the available mounting geometry and
   likely the dominant vibration frequencies at any given point. Pick a
   clean, flat, adhesive-friendly spot as close to the gearbox/motor
   coupling as accessible, note exactly where in `config.json`/`channel_map`
   (see [137A.md § 9](137A.md#9-record-the-channel-map)), and flag it in the
   deployment notes so it can be reconciled against later 117A installs.
3. **Panel removal order and fasteners.** Don't assume 137A panel part
   numbers or fastener types — confirm against the physical unit before
   forcing anything.
4. **Cabinet size affects clearance and cable routing**, not the placement
   logic itself — expect tighter routing for CT leads, opto taps, and probe
   cables inside the smaller cabinet, and budget more care in dressing cable
   away from the belt/gearbox and any hot surfaces.

## Everything else

Follow [137A.md](137A.md) steps 1 (bench provisioning), 3 (CT install), 6
(temperature probes — same targets), 7 (leak-sensing add-ons), 8 (cable
routing), 9 (record channel map), 10 (close-up/verify), 11 (journaling
sticker/briefing), and 12 (pickup) as written, adapting only for the
smaller cabinet's physical clearances. The [expected-signals table](137A.md#expected-signals-on-a-healthy-machine)
in the 137A guide is a reasonable starting baseline for the 117A too, but
has **not** been validated against a real 117A yet — treat it as provisional
alongside the rest of this document.

## See also

- [137A.md](137A.md) — base procedure
- [../safety.md](../safety.md)
- [../hardware/wiring-and-pinmap.md](../hardware/wiring-and-pinmap.md)
- [../firmware/data-format-spec.md](../firmware/data-format-spec.md)
