# Install guide — Frosty Factory 127A (delta from 137A)

> **PROVISIONAL — re-verify against the 127A service manual during the
> first install.** Source:
> [rf_service_man._127a__w_new_2016.pdf](https://www.frostyfactory.com/downloads/rf_service_man._127a__w_new_2016.pdf).
> This document has not yet been checked against a physical 127A or that
> manual in detail; treat every part number and placement note below as a
> starting point, not a confirmed fact, until the first field install closes
> the loop. Update this banner and the notes below once that's done.

This is a **delta** document. Follow [137A.md](137A.md) as the base
procedure, including its safety gate, panel-removal order, and general
placement logic — only the differences below apply. Read
[../safety.md](../safety.md) first regardless.

## What's different on the 127A

| Aspect | 137A (base) | 127A |
|---|---|---|
| Cabinet width | narrower | 26" (wider than 137A) |
| Drive architecture | Belt-driven Franklin motor + flywheel | **Oriental motor (F1210) + gearbox (F1211)** — not the Franklin belt drive |
| TCC microswitch | F0346 | Same, **F0346** |
| Transformer | F4995 | **F4997** |
| Condenser air intake | Rear | **Underneath the machine (updraft), through mandatory skirts** |
| Condenser air discharge | Sides | Sides (same as 137A) |
| Water-cooled variant | n/a | **127W exists — out of scope for this guide; flag and stop if encountered** |

## What stays the same

- TCC microswitch is the same part (F0346) as the 137A — the opto-3 tap
  described in [137A.md § 4](137A.md#4-ac-presence-taps) applies without the
  caveats needed on the 117A.
- 24V control chain is otherwise the same: contactor (F0478), HP switch
  (F0661) — only the transformer part number differs (F4997 vs F4995), which
  has no bearing on install steps.
- CT clamp placement logic (one conductor per clamp) is unchanged.

## What needs on-site judgment

> **WARNING:** All notes below assume the machine is unplugged and locked
> out per [../safety.md](../safety.md), same as the 137A procedure.

1. **Pod-A (beater drive) location and axes differ.** The 127A drive is an
   Oriental motor (F1210) direct to a gearbox (F1211) — there is no
   flywheel/belt arrangement to anchor against as in the 137A guide. Choose
   a mounting spot on the motor or gearbox body: clean, flat, adhesive- or
   epoxy-stud-friendly, and as rigidly coupled to the drive as possible.
   Because the drive geometry differs from the belt/flywheel case, the
   dominant vibration axes at that mount point may not map 1:1 onto the
   137A's X/Y/Z convention — note the actual mounting orientation in
   `config.json`/`channel_map` (see
   [137A.md § 8](137A.md#8-record-the-channel-map)) so analysis can
   correctly interpret axis data for 127A installs.
2. **Condenser air-in probe location is different, not just relocated —
   check that skirts are installed first.** The 127A draws condenser air
   from **underneath the machine** (updraft) through mandatory skirts, not
   from the rear as on the 137A. This changes both where DS18B20 #2
   (condenser air-in) goes and adds an install-checklist item:
   - Confirm the machine's skirts are installed and intact **before**
     placing the probe or closing up. Missing or damaged skirts degrade
     freeze performance directly (the machine loses its intended air path)
     and will also make DS18B20 #2 readings unrepresentative of true intake
     air.
   - Mount DS18B20 #2 at the skirt/under-machine intake path, not at the
     rear.
   - Side discharge (DS18B20 #3) placement is unchanged from the 137A
     guide.
3. **127W (water-cooled variant): stop if encountered.** If the unit turns
   out to be a water-cooled 127W rather than air-cooled 127A, this guide
   does not apply — condenser cooling, and therefore probe placement and
   possibly current-draw signatures, are different in ways not covered
   here. Flag this to the project owner rather than improvising an install.
4. **Wider cabinet (26")** eases cable routing relative to the 117A but
   still confirm clearances before assuming 137A routing distances apply
   directly.

## Everything else

Follow [137A.md](137A.md) steps 1 (bench provisioning), 3 (CT install), 6
(temperature probes — same targets except condenser air-in per above), 7
(cable routing), 8 (record channel map), 9 (close-up/verify — including
confirming skirts are in place, not just side/rear clearance), 10
(journaling sticker/briefing), and 11 (pickup) as written. The
[expected-signals table](137A.md#expected-signals-on-a-healthy-machine) in
the 137A guide is a reasonable starting baseline for the 127A too, but has
**not** been validated against a real 127A yet — treat it as provisional
alongside the rest of this document, and note that condenser ΔT behavior
in particular may look different given the updraft air path.

## See also

- [137A.md](137A.md) — base procedure
- [../safety.md](../safety.md)
- [../hardware/wiring-and-pinmap.md](../hardware/wiring-and-pinmap.md)
- [../firmware/data-format-spec.md](../firmware/data-format-spec.md)
