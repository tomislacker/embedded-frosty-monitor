# ADR 0001: Build a portable diagnostic DAQ before any permanently-installed monitor

## Status

Accepted

## Context

Frosty Factory 117A/127A/137A machines fail in ways that are hard to
diagnose from a single service visit: compressor short-cycling, a beater
that never satisfies the TCC microswitch and so never freezes, a clogged
condenser, knocking during freeze-down, belt slip, a leaking rear seal,
motor degradation, refrigerant loss. Most of these show up intermittently
over hours or days, not during the few minutes a tech is standing in front
of the machine.

We do not yet know what the real vibration, current, and temperature
signatures of these failure modes look like in practice. We also do not
have per-machine cost pressure driving us toward a minimal BOM yet — we
have one, maybe a few, machines to learn from, not a fleet to instrument
permanently.

## Decision

Build a portable, temporarily-installed diagnostic unit first. One unit is
carried between machines by a tech, installed for the duration of a
diagnostic case (days to weeks), then pulled and its data analyzed
offline. No permanently-installed monitor is built at this stage.

## Consequences

One unit can serve many machines, which keeps the up-front hardware cost
low while the failure signatures themselves are still unknown. It also
means the unit is unpowered and absent from a machine most of the time,
so it never becomes an ongoing point of failure or maintenance burden on
customer equipment.

The tradeoff: no machine gets continuous, ongoing monitoring under this
plan, and every deployment costs a truck roll to install and another to
retrieve. A permanently-installed monitor, with a cost-reduced BOM
justified by real failure-signature knowledge, is deferred to v2 — see
[docs/roadmap.md](../roadmap.md).
