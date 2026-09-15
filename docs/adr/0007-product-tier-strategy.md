# ADR 0007: One platform, four product tiers

## Status

Accepted

## Context

[ADR 0001](0001-portable-daq-first.md) committed to building a portable
diagnostic unit (now Tier 3 — DAQ Pro) before anything permanently
installed, on the reasoning that we didn't yet know the real failure
signatures and didn't have fleet-scale cost pressure. DAQ Pro is now
built ([docs/hardware/bom.md](../hardware/bom.md), M0 firmware complete),
and the customer conversation it enables (see
[proposal/service-proposal.html](../../proposal/service-proposal.html)) has
surfaced a spread of budgets and deployment models we can't serve with one
SKU: some customers want the deepest diagnostic depth on-demand, some want
a light always-on signal on every machine at minimum cost, and some want
continuous remote visibility with real-time alerts. A single BOM point
can't be simultaneously cheap enough for "one on every machine" and rich
enough for "portable diagnostic depth" or "real-time remote."

## Decision

Build one platform across four hardware tiers, differing only in sensing
density, storage, and transport, not in data format, firmware HAL, or
analysis stack:

- **Tier 1 — Guard.** Cheapest producible, permanent install, every
  machine. ESP32-C3, one CT, two DS18B20, drip counter. Internal-flash
  rolling log, BLE walk-up readout. No SD, no RTC.
- **Tier 2 — Logger.** Guard plus microSD, RTC, a second CT, and one
  vibration pod. Permanent install with richer trend history.
- **Tier 3 — DAQ Pro.** The existing portable diagnostic unit, unchanged
  by this decision — full 17-channel sensing, `SdSink` storage.
- **Tier 4 — Live.** DAQ Pro-class sensing plus a `CloudSink` to AWS IoT
  Core, WiFi or cellular, for real-time remote visibility and alerting.

Full tier definitions, BOMs, and the build-out sequence live in
[docs/product-line.md](../product-line.md); this ADR records the strategic
decision, not the tier-by-tier detail.

Every tier shares the same on-card/on-wire data format and the same
`IStorageSink` transport abstraction from
[ADR 0002](0002-microsd-storage-with-transport-abstraction.md) — Guard and
Logger are a firmware HAL *subset* build (fewer channels, different sink),
not a different codebase. Every tier's data feeds the same
signature-detection suite in the analysis pipeline (see
[docs/roadmap.md](../roadmap.md), item 2): a compressor short-cycling
detector doesn't care whether the current channel came from a Guard unit or
a DAQ Pro unit, only that it's the same channel in the same format.

## Consequences

The shared data format and analysis stack means premium tiers subsidize
cheap tiers: DAQ Pro and Live's richer sensing is what lets us derive and
validate failure-signature thresholds in the first place, and Guard/Logger
ship those same thresholds at a coarser sampling density instead of having
to re-derive them from scratch on thinner data. This is why the build-out
sequence in [docs/product-line.md](../product-line.md) goes top-down
(DAQ Pro → Live → Logger → Guard) rather than bottom-up or in parallel —
building Guard first would mean guessing at thresholds with no
higher-fidelity tier to calibrate against.

It also means one firmware HAL, one on-card/on-wire format, and one
analysis pipeline to maintain instead of four, at the cost of a real
engineering constraint: any change to the shared interfaces (`IStorageSink`,
the record format, a detector's input channel set) has to consider every
tier, not just the one currently being worked on. The ESP32-C3 port for
Guard/Logger is not yet built — it is a roadmap item (see
[docs/roadmap.md](../roadmap.md)) — and until it lands, Guard and Logger
are designed and costed, not shippable.

This does not change or supersede [ADR 0001](0001-portable-daq-first.md):
DAQ Pro's build-portable-first reasoning is exactly why DAQ Pro exists to
be the calibration source for the other three tiers.

## Alternatives considered

**Single mid-range product.** One SKU, one BOM point, priced and sensed
between Guard and Logger. Rejected: it satisfies neither end of the
spread. It's too expensive to put on every machine at the volume Guard
targets, and too thin on sensing to serve either the deep portable
diagnostic case (DAQ Pro) or the real-time remote case (Live). A single
mid-range product also has no obvious calibration source of its own —
Tier 3/4's richer data is what makes Guard/Logger's coarse thresholds
trustworthy rather than guessed.

**Separate bespoke products per segment.** Build genuinely different
hardware, firmware, and analysis pipelines tuned to each customer segment
independently, rather than one platform with tier-scoped subset builds.
Rejected: it multiplies firmware maintenance to one codebase per product
instead of one HAL with per-tier compile-time selection, it forfeits the
calibration-transfer argument above (each bespoke product would need
independent field validation of its own thresholds, from its own data,
with no shared detector suite to lean on), and it multiplies the analysis
pipeline the same way — a distinct detector implementation per bespoke data
format instead of one detector suite reading one format regardless of
which tier produced it.
