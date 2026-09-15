# ADR 0002: microSD storage for MVP, behind a transport abstraction

## Status

Accepted

## Context

The unit needs to persist days to weeks of vibration, current, temperature,
and control-state data with no guarantee of network connectivity at the
install site, and it needs to hand that data off to a tech who is not
expected to run any special software to retrieve it. At roughly 25-30MB/day
(see [docs/firmware/data-format-spec.md](../firmware/data-format-spec.md)),
a 32GB card lasts months.

At the same time, offload over BLE to a phone, or over WiFi to the cloud,
are both plausible future requirements once the base logger is proven out
(see [docs/roadmap.md](../roadmap.md)), and we don't want the storage
mechanism baked into every sensor task's code.

## Decision

MVP storage is a microSD card, swapped by hand: pull the card, read it on
any computer, no companion app or network required. All record emission in
firmware goes through a single `IStorageSink` interface; `SdSink` is the
only implementation shipped in the MVP. The on-card layout is
self-describing — a manifest, daily channel CSVs, binary vibration bursts,
a vibration summary CSV, and a JSONL event log — so a card is readable on
its own with no external schema lookup. See
[data-flow.md](../architecture/data-flow.md) for how records reach the
sink.

## Consequences

Retrieval requires physically visiting the machine to pull the card, which
is consistent with the portable, visit-based deployment model in
[ADR 0001](0001-portable-daq-first.md). The self-describing card format is
part of the contract other tools rely on: the analysis pipeline reads it
directly, and any future sink still has to produce something equivalent to
this format downstream.

Because every producer task only ever talks to `IStorageSink`, adding
`BleSink` (phone offload) or `CloudSink` (WiFi/cloud) later is additive —
a new sink implementation — rather than a rewrite of sensor or scheduling
code. That is the whole reason the interface exists in the MVP even though
only one implementation ships now.
