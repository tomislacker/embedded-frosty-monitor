# ADR 0004: Modular logger core plus sacrificial sensor pods

## Status

Accepted

## Context

Parts of this unit have to physically sit inside a frozen-drink machine:
near the beater drive, on the compressor shell, in the airstream, on the
cylinder jacket. That environment means exposure to grease and sugar
contamination that is difficult or impossible to fully clean off a
sensor once it's been in place for days or weeks. The electronics that do
the actual compute, storage, and power regulation, by contrast, don't need
to be anywhere near that contact and benefit from staying intact and
reusable across many installs.

## Decision

Split the hardware into a reusable **logger core** — the ESP32-S3, ADC,
RTC, SD card, thermocouple amp, and I2C buffer, in a sealed IP65 enclosure
— and cheap, detachable **sensor pods** on connectorized cables: the two
ADXL345 vibration pods, the CT clamps, and the 1-Wire temperature probes.
Pods are treated as consumable; the core is not.

## Consequences

A contaminated or physically damaged pod gets replaced for a few dollars
of parts without touching the core electronics, and a single core serves
many installs and many machines over its life, consistent with
[ADR 0001](0001-portable-daq-first.md). Connectorized cabling makes
install and retrieval faster since pods can be pre-run and left in place
between visits if a machine gets a longer-term deployment.

The known tradeoff is the vibration pods: running I2C to the ADXL345s over
30-80cm of shielded Cat5e outside the enclosure is well beyond I2C's
comfortable range, and requires active buffering (P82B715) at the core end
to stay reliable. If that proves insufficiently robust in the field, the
documented fallback is to move the bus logic into the pod itself — an
RS-485 link with a Seeed XIAO RP2040 bridging I2C to RS-485 in-pod — which
is a real design change to that specific pod, not the whole core-and-pod
model. See [docs/roadmap.md](../roadmap.md) for bench validation of this
tradeoff.
