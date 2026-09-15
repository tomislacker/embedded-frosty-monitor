# Roadmap

Ordered, post-MVP. Nothing here blocks M0-M5 (see [README.md](../README.md)
for the milestone list); this is what comes after the base unit is proven
on hardware.

## 1. Bench-validation items deferred from M0

- **24VAC opto trigger threshold.** The opto-isolated input on the
  contactor coil needs its trigger threshold validated on the bench against
  real 24VAC transformer output, including sag under load, so it reliably
  reads "coil energized" without false triggers.
- **I2C-over-cable vs. RS-485 fallback.** The buffered I2C run to the
  vibration pods (30-80cm shielded Cat5e via P82B715) needs bench
  validation for reliability before it's trusted in the field; if it's
  marginal, fall back to the RS-485 + XIAO RP2040 in-pod design documented
  in [ADR 0004](adr/0004-modular-logger-core-plus-sacrificial-pods.md).
- **CT headroom vs. compressor locked-rotor amps.** Confirm the
  SCT-013-020 clamps and ADS1115 gain settings have enough headroom to
  capture compressor locked-rotor/inrush current without clipping, not
  just steady-state run current.
- **SD fsync cadence tuning.** The ~5s fsync interval in
  `StorageWriterTask` is a starting point; tune it against real write
  throughput and card wear characteristics once bursts and channel logs
  are both running at once.

## 2. Signature-detection implementations in analysis

One detector per known failure mode, using the logged channels:

- Compressor short-cycling
- TCC never satisfied (won't freeze)
- Clogged condenser / poor ventilation (condenser air ΔT)
- Knocking during freeze-down (ice or air in the cylinder)
- Belt loss or slip
- Rear-seal failure (drip)
- Motor degradation
- Refrigerant loss

## 3. BLE-to-phone offload

A second `IStorageSink` implementation (`BleSink`, per
[ADR 0002](adr/0002-microsd-storage-with-transport-abstraction.md)) plus a
companion phone app, so a tech can pull recent data without opening the
enclosure or removing the SD card — useful for a quick mid-deployment
check without disturbing the install.

## 4. WiFi/cloud upload

A `CloudSink` built around AWS IoT Core: a per-device X.509 certificate, an
MQTT topic per deployment, and chunked upload of rotated files as they
close, landing in Timestream or S3+Athena for downstream analytics. This
is explicitly gold-plating until field value is proven — it adds
infrastructure and ongoing cost for a workflow the SD-card-swap MVP
already covers; it's worth building once there's a real case for
near-real-time or fleet-wide visibility, not before.

## 5. v2 permanent-install monitor

A cost-reduced BOM, likely a custom PCB instead of dev-board-plus-breakouts
(see [ADR 0003](adr/0003-esp32-s3-devkitc-1-platform.md)), and power drawn
safely from the machine itself instead of an external adapter. This is the
natural next step once portable deployments (per
[ADR 0001](adr/0001-portable-daq-first.md)) have produced enough
failure-signature data to justify leaving a unit in a machine permanently.

## 6. Other manufacturers/models expansion

Extend sensor placement guidance and failure-signature detectors beyond
the Frosty Factory 117A/127A/137A line to other frozen-drink machine
manufacturers and models, once the detection logic has proven itself on
the machines this project started with.

## 7. Leak-sensing bench validation & threshold tuning

Seal-leak drip sensing is **now in scope**: the IR slot-type optical drop
counter at the drip tube outlet ships in the base config (see
[docs/hardware/bom.md](hardware/bom.md) and
[docs/hardware/wiring-and-pinmap.md](hardware/wiring-and-pinmap.md)), giving
a direct, quantitative rear-seal-wear signal (`drip_rate_cpm`) instead of
relying on indirect inference from other channels. The under-machine
moisture pad and the refrigerant gas sensor remain optional add-ons on top
of that base sensor, not part of the base config.

What's still open:

- **Gas-sensor bench validation.** The refrigerant gas-sensor add-on is
  experimental — cheap semiconductor modules drift and cross-react with
  other vapors. Bench-validate before presenting its data to a customer;
  until then, refrigerant-loss detection continues to rely on the indirect
  signature (compressor short-cycling + reduced condenser ΔT).
- **Drip-rate alert threshold calibration.** Establish what `drip_rate_cpm`
  counts as healthy (occasional single drops during cleaning) versus a
  genuine seal-wear signature, using field data across the three chassis
  sizes.
