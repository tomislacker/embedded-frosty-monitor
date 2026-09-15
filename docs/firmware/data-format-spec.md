# On-card data format specification — v1

This is the canonical, exact on-card data format for frosty-monitor. It is
schema_version 1. Both firmware (`StorageWriterTask` /
[architecture.md](architecture.md)) and the offline analysis pipeline
(`analysis/`) build to this document — if either disagrees with it, that is
a bug in that code, not a reason to reinterpret the spec.

See [ADR 0002](../adr/0002-microsd-storage-with-transport-abstraction.md)
for why the on-card layout is self-describing, and
[data-flow.md](../architecture/data-flow.md) for how records reach the card
through `IStorageSink`.

## Design constraints

- **Self-describing card.** Everything needed to interpret the data — units,
  calibration, deployment identity, effective config — lives on the card
  itself in `manifest.json`. A card should be fully interpretable with no
  external schema lookup and no network access.
- **Every record/file is an independently transmittable unit.** This is a
  deliberate constraint, not an accident of the SD-first MVP: a single CSV
  row, a single JSONL line, a single vibration `.bin` file, and a single
  manifest are each self-contained enough to be the unit of transfer for a
  future chunked BLE or WiFi upload, without redesigning the format. Nothing
  in this spec relies on cross-referencing byte offsets between files.
- **Readers must tolerate unknown extra CSV columns appended after the
  canonical ones.** A future firmware version may append new columns to the
  end of `channels_YYYYMMDD.csv` or `vib_summary_YYYYMMDD.csv` rows. Analysis
  code must read the canonical columns by name/position from the front and
  must not fail or truncate on additional trailing columns it doesn't
  recognize.
- **Versioning policy.** `schema_version` in `manifest.json` is bumped only
  for a **breaking** change to an existing field's meaning, an existing
  column's position, or removal of a column/field — i.e., any change an old
  reader could not safely ignore. Purely additive changes (new trailing CSV
  columns, new optional JSON keys, new `type` values in `events`) do **not**
  bump `schema_version`; readers are required to tolerate those per the
  point above.

## Card root layout

```
/manifest.json
/config.json
/channels_YYYYMMDD.csv          (one per day)
/events_YYYYMMDD.jsonl           (one per day)
/vibration/vib_<pod>_<ts_unix_ms>.bin   (one per captured burst)
/vibration/vib_summary_YYYYMMDD.csv     (one per day)
```

### `manifest.json`

Written once at deployment start by `ConfigLoader`. Contains deployment
identity plus the **effective**, resolved configuration — including any
values inherited from firmware defaults rather than explicitly set in
`config.json` — so the card is self-describing even if `config.json` is
later lost or edited.

```json
{
  "schema_version": 1,
  "deployment_id": "string",
  "machine_model": "117A | 127A | 137A | other",
  "machine_serial": "string",
  "technician": "string",
  "firmware_version": "string",
  "start_ts_iso": "string, UTC ISO-8601",
  "channel_map": {
    "<sensor id>": {
      "location": "string, physical location description",
      "calibration": "sensor-appropriate calibration value(s)"
    }
  },
  "config_effective": {
    "sample_rates": "…",
    "burst_settings": "…"
  }
}
```

`channel_map` entries describe physical location plus whatever calibration
that sensor type needs, for example:

| Sensor | Calibration field |
|---|---|
| CT clamp | amps-per-volt |
| ADXL345 | g-per-LSB |
| DS18B20 | ROM address → location mapping |
| Thermocouple (MAX31855) | cold-junction/offset correction |

### `config.json`

Technician-authored input: deployment metadata and any sample-rate/burst
overrides, written before or during bench provisioning (see the `ID` and
`SETTIME` CLI commands in [architecture.md](architecture.md#configloader-boot--cli)).
Firmware reads this at boot and echoes the **effective** values — including
values not explicitly present in `config.json` — into `manifest.json`.
`config.json` is not itself required to be complete or present after boot;
`manifest.json` is the record of truth for what actually ran.

### `channels_YYYYMMDD.csv`

Rotated daily at the UTC day boundary. One row per second. Header, exactly:

```
ts_iso,ts_unix_ms,current_beater_a,current_compressor_a,temp_cylinder_c,temp_cond_in_c,temp_cond_out_c,temp_ambient_c,temp_hopper_c,temp_discharge_c,beater_on,compressor_cmd,tcc_satisfied,hp_ok,drip_rate_cpm,moisture_raw,refrigerant_raw
```

| Column | Type | Notes |
|---|---|---|
| `ts_iso` | string | UTC ISO-8601 |
| `ts_unix_ms` | integer | Unix epoch milliseconds |
| `current_beater_a` | float | amps, beater-motor leg |
| `current_compressor_a` | float | amps, compressor leg |
| `temp_cylinder_c` | float | °C, freezing-cylinder jacket |
| `temp_cond_in_c` | float | °C, condenser air intake |
| `temp_cond_out_c` | float | °C, condenser air discharge |
| `temp_ambient_c` | float | °C, ambient inside compartment |
| `temp_hopper_c` | float | °C, hopper (optional probe) |
| `temp_discharge_c` | float | °C, compressor discharge line (thermocouple) |
| `beater_on` | 0/1 | AC-presence, beater leg |
| `compressor_cmd` | 0/1 | AC-presence, contactor coil |
| `tcc_satisfied` | 0/1 | TCC microswitch state, if tapped |
| `hp_ok` | 0/1 | High-pressure switch state, if tapped |
| `drip_rate_cpm` | float | drops/minute at the drip tube, rolling window (v1.1) |
| `moisture_raw` | float | 0.0-1.0 normalized, under-machine moisture pad, uncalibrated (optional add-on, v1.1) |
| `refrigerant_raw` | float | 0.0-1.0 normalized, refrigerant gas sensor, uncalibrated and **EXPERIMENTAL** -- not a calibrated ppm reading (optional add-on, v1.1) |

A missing/unwired sensor leaves its field **empty**, not zero. Booleans are
always `0` or `1`, never `true`/`false`. `ts_iso` is always UTC.

#### v1.1 additions

`drip_rate_cpm`, `moisture_raw`, and `refrigerant_raw` were appended after
`hp_ok` to add leak-detection channels: an IR slot-type optical drop counter
at the machine's drip tube (rear-seal product-leak telltale), plus two
optional ADS1115 add-on channels (under-machine capacitive moisture pad,
compressor-compartment refrigerant gas sensor). See `firmware/src/pins.h`
for the pin/channel assignments.

- `drip_rate_cpm` is always populated (the drop counter is on-board, not an
  optional add-on); it reads `0.000` when no drops have been seen in the
  rolling window, not empty.
- `moisture_raw`/`refrigerant_raw` follow the same missing-sensor convention
  as every other channel: an absent/unconfigured add-on leaves the field
  **empty**, not `0.000`.
- Both are raw normalized readings, not calibrated physical units --
  `refrigerant_raw` in particular must never be presented as calibrated ppm.

This is a purely additive, non-breaking change per the versioning policy
above: the three columns are appended strictly after the existing canonical
ones, `schema_version` stays `1`, and it exercises exactly the append-only
forward-compat rule this spec commits readers to -- a reader written against
the v1 (14-column) header must keep working unmodified against this
17-column header, reading the columns it knows by name/position from the
front and ignoring the three trailing ones it doesn't recognize.

### `events_YYYYMMDD.jsonl`

Rotated daily. One JSON object per line (JSON Lines, not a JSON array):

```json
{"ts_iso": "string", "ts_unix_ms": integer, "type": "button|system|trigger|error", "detail": {}}
```

`type` values:

| `type` | Meaning |
|---|---|
| `button` | Physical event-journal button press |
| `system` | Firmware lifecycle (boot, config load, rotation, etc.) |
| `trigger` | Automatic capture trigger fired (e.g. current spike) |
| `error` | A logged fault condition |

`detail` is free-form per `type` and may gain new keys over time without a
`schema_version` bump, per the versioning policy above.

### `vibration/vib_<pod>_<ts_unix_ms>.bin`

One binary file per captured burst (periodic or triggered — not every
rolling capture window, since most windows only ever produce a summary
record; see [architecture.md](architecture.md#vibrationcapturetask-priority-4)).
Little-endian throughout. A packed 32-byte header, followed by the sample
payload.

| Offset | Size | Field | Notes |
|---|---|---|---|
| 0 | 4 bytes | `magic` | ASCII `"FVB1"` |
| 4 | 1 byte | `format_version` | `1` |
| 5 | 1 byte | `pod_id` | `1` = beater-drive pod, `2` = compressor pod |
| 6 | 2 bytes | `reserved` | `0` |
| 8 | 4 bytes | `sample_rate_hz` | uint32 |
| 12 | 4 bytes | `n_samples` | uint32, samples per axis |
| 16 | 1 byte | `n_axes` | uint8, `3` |
| 17 | 3 bytes | `reserved` | `0, 0, 0` |
| 20 | 8 bytes | `start_ts_unix_ms` | uint64 |
| 28 | 4 bytes | `scale_g_per_lsb` | float32 |
| 32 | — | payload | `n_samples × n_axes` × int16, interleaved X, Y, Z |

The payload is interleaved per-sample, not per-axis: sample 0's X, sample
0's Y, sample 0's Z, sample 1's X, and so on — `n_samples × n_axes` int16
values total, each `int16 = round(raw_g / scale_g_per_lsb)`.

### `vibration/vib_summary_YYYYMMDD.csv`

Rotated daily. One row per burst (both periodic and triggered bursts get a
summary row; only the raw `.bin` capture is selective). Header, exactly:

```
ts_iso,ts_unix_ms,pod_id,rms_x_g,rms_y_g,rms_z_g,peak_x_g,peak_y_g,peak_z_g,band_low_g2,band_mid_g2,band_high_g2
```

| Column | Type | Notes |
|---|---|---|
| `ts_iso` | string | UTC ISO-8601, burst start |
| `ts_unix_ms` | integer | Unix epoch milliseconds, burst start |
| `pod_id` | integer | `1` = beater-drive pod, `2` = compressor pod |
| `rms_x_g`, `rms_y_g`, `rms_z_g` | float | RMS acceleration per axis, g |
| `peak_x_g`, `peak_y_g`, `peak_z_g` | float | Peak acceleration per axis, g |
| `band_low_g2`, `band_mid_g2`, `band_high_g2` | float | FFT band energy — 5–50Hz, 50–300Hz, 300–800Hz respectively, g² |

`ts_unix_ms` in this file is the value to join against the corresponding
`vib_<pod>_<ts_unix_ms>.bin` filename for a triggered/periodic burst that
also produced a raw capture.

## Cross-references

- Task-level detail on when each record type is produced:
  [architecture.md](architecture.md).
- End-to-end path from sensor read to file on card, including the queue and
  `IStorageSink` boundary: [data-flow.md](../architecture/data-flow.md).
- Storage volume math behind the daily rotation cadence:
  [architecture.md — Storage budget](architecture.md#storage-budget).
