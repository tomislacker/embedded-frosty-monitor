# ADR 0006: Journal button is the record; QR form enrichment is optional

## Status

Accepted

## Context

Anyone standing at the machine — usually a restaurant employee, not a
technician — sometimes notices something worth flagging: a knock, a smell,
the machine doing something odd right now. They need a "see something, say
something" action that marks the moment without breaking off to write
notes or pull out a phone mid-task. Later, during analysis, that timestamp
needs to be findable and, ideally, enrichable with more context: a photo,
a video, a few lines about what was observed. Because different employees
across shifts will be the ones reporting, the supporting documentation
must land in one shared dataset — not scattered across whichever phone
happened to capture it.

## Decision

A press of the event button is a complete, first-class incident report on
its own: a timestamped JSONL marker, written through the same storage path
as every other record (see [data-flow.md](../architecture/data-flow.md)).
Nothing else is required for the press to be useful. A QR code sticker on
the enclosure separately opens a **cloud-hosted** web form — a Google Form
initially, which supports photo/video upload and collects every response
into one central spreadsheet/drive — for **optional** enrichment. Cloud
hosting is a requirement, not an implementation detail: reports from many
employees across shifts must accumulate in a single shared dataset, never
in per-phone silos. Analysis correlates form submissions to the nearest
button-press timestamp after the fact. When a cloud telemetry backend
exists (see [docs/roadmap.md](../roadmap.md)), the form's successor lives
there alongside the machine data.

## Consequences

The tech is never blocked on connectivity, a phone, or remembering a
procedure to flag a moment — one debounced button press is enough, and it
degrades gracefully to "just a timestamp" if enrichment never happens.
Enrichment is decoupled from the firmware and the card format entirely: it
lives in a separate system (the form response and any attached media) and
is joined to the log data during analysis, not on-device.

The cost on the firmware side stays minimal: one debounced button and one
JSONL record type, no on-device text entry or media capture to build or
maintain. The cost is pushed to analysis, which has to do the
timestamp-correlation join between button presses and form submissions;
see [docs/roadmap.md](../roadmap.md).
