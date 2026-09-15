# frostsight cloud — premium real-time tier backend

> ## ⚠️ STATUS: SKELETON — NEVER APPLIED
>
> Everything under `cloud/` is infrastructure-as-code and documentation
> only. **No `terraform apply` has ever been run against this
> configuration, against any AWS account.** There is no live IoT Core
> endpoint, no S3 bucket, no Glue database, nothing deployed anywhere.
>
> This exists to be **reviewed by Ben**, not trusted blind. It requires
> **your own AWS account** and deliberate, informed `terraform apply` /
> `provision-device.sh` runs to become real. Read `cloud/terraform/*.tf`
> (heavily commented on purpose) and `docs/cloud/architecture.md` before
> running anything below.
>
> Nothing in this tier is required for frosty-monitor's SD-card MVP to
> work. See [docs/roadmap.md](../docs/roadmap.md) item 4 for where this
> fits relative to everything else, and
> [docs/cloud/architecture.md](../docs/cloud/architecture.md) for why the
> SD card remains the source of truth even once this is deployed.

## What's here

```
cloud/
  terraform/            # Terraform skeleton (see file-by-file comments)
    providers.tf         # provider + version pin, no backend configured
    variables.tf          # region / name_prefix / alert_email / alert_phone / thresholds
    locals.tf              # account/region lookups, shared naming — the ONLY place
                            #   account identity enters this config
    iot_core.tf            # IoT thing type + least-privilege device policy
    ingest.tf               # S3 bucket + lifecycle, Firehose, both IoT topic rules
    query.tf                  # Glue database + table over the channels JSON
    alerting.tf                # SNS topic/subscriptions + example threshold alert rule
    outputs.tf                  # names/ARNs other tooling (provision-device.sh) can reference
  scripts/
    provision-device.sh    # create one device's IoT identity (thing + cert/key + policy)
    deprovision-device.sh   # reverse of the above
  README.md                     # this file
```

See also [docs/cloud/architecture.md](../docs/cloud/architecture.md) for
the design doc — diagram, security model, multi-tenancy considerations,
dashboard options, and what "real-time" actually means here.

## Prerequisites

- An AWS account you (Ben) control, with permission to create IoT Core,
  S3, Kinesis Firehose, Glue, IAM, and SNS resources.
- [Terraform](https://developer.hashicorp.com/terraform) >= 1.5, < 2.0
  (this was written/validated against 1.15).
- AWS CLI v2, configured with credentials for that account
  (`aws sts get-caller-identity` should succeed).
- `jq` and `curl` (used by `provision-device.sh`).
- `shellcheck`, if you want to re-lint the scripts after editing them
  (they're shellcheck-clean as written).
- A decision on **where Terraform state will live** before the first real
  `apply` — this skeleton deliberately has no `backend` block (see
  `providers.tf`). Local state is fine for solo review; an S3+DynamoDB
  backend is the usual answer once this is real. That decision is
  intentionally left to you rather than baked in.

## Bring-up, step by step

**1. Review, don't skip.** Read every `.tf` file's comments — they're
written for exactly this review, not just as decoration. Pay particular
attention to the loud warning at the top of `terraform/query.tf`: the
Glue table's column names are this side's best guess at the aggregate
JSON schema, written without sight of `docs/firmware/connectivity.md`.
Reconcile them before trusting any Athena query against real data.

**2. Choose a state backend (or explicitly decide not to, for now).**
Either add a `backend` block to `terraform/providers.tf` yourself
(S3+DynamoDB is the standard choice) or proceed with local state
understanding that it lives only on your machine.

**3. `terraform init`**

```sh
cd cloud/terraform
terraform init
```

This downloads the pinned `hashicorp/aws` provider. It does not touch AWS
itself.

**4. `terraform plan`, with real values for the required variables:**

```sh
terraform plan \
  -var 'alert_email=you@example.com' \
  -var 'region=us-east-1' \
  -var 'name_prefix=frostsight'
```

(Or put these in a `terraform.tfvars` — already gitignored by
`terraform/.gitignore` so you don't accidentally commit an email address
or phone number.) **Read the plan output.** Confirm you recognize every
resource it proposes to create and that the account/region are what you
expect (`aws sts get-caller-identity`, `aws configure list`).

**5. `terraform apply`** — only once you're satisfied with the plan. This
is the first point at which anything actually gets created in AWS.

```sh
terraform apply -var 'alert_email=you@example.com'
```

Confirm the SNS subscription email that arrives immediately after — no
alerts are delivered until it's clicked.

**6. Provision a device:**

```sh
cd ../scripts
./provision-device.sh -n delta117a-001 -r us-east-1
```

This creates the IoT thing, mints a certificate/key pair, attaches the
shared device policy, and writes `ca.pem` / `device.pem` / `device.key`
into `./provisioned/delta117a-001/certs/` — copy the **contents** of that
`certs/` directory onto the unit's SD card at `/certs/`. See the script's
header comment for idempotence notes and `deprovision-device.sh` for the
reverse/cleanup path.

**7. Point the firmware at it.** The script prints the account's IoT data
endpoint (`iot:Data-ATS` type) and the thing name. Both go into the
device's `config.json` per whatever key names
[docs/firmware/connectivity.md](../docs/firmware/connectivity.md) settles
on for the MQTT broker host and client ID / topic device-id segment —
this repo's cloud side doesn't own that file, so the exact key names
aren't repeated here; the *values* are:

- MQTT broker host: the endpoint printed by `provision-device.sh`
  (`aws iot describe-endpoint --endpoint-type iot:Data-ATS` under the
  hood), port 8883.
- Client ID / device-id / topic namespace segment: the thing name you
  passed to `-n`.
- TLS materials: `ca.pem`, `device.pem`, `device.key` as written to
  `/certs/`.

## Cost model

**Assumption, per the task this was built against:** one device
publishing one ~1KB aggregated JSON message per minute on
`frostsight/<device_id>/channels`, continuously, all month, plus a small,
conservatively-padded allowance for the occasional `.../events` and
`.../vibration` summary messages. All prices below are US East (N.
Virginia) list prices pulled from the AWS pricing pages at the time this
was written — **verify current figures at
[aws.amazon.com/pricing](https://aws.amazon.com/pricing/)** before trusting
them for a real budget; AWS revises prices without much notice and this
document does not get updated automatically.

**Volume, one device, one 30-day month:**

- Channel messages: 1/min × 60 × 24 × 30 = **43,200 messages**, ~1KB each
  → ~42MB/month raw.
- Connection time: assume the device stays connected essentially the
  whole month → **43,200 connection-minutes**.
- Events/vibration-summary messages: occasional, folded into the
  padding below rather than modeled individually — they're a small
  fraction of the channels volume by design.

| Line item | Basis | Rate (verify at aws.amazon.com/pricing) | Monthly cost/device |
|---|---|---:|---:|
| IoT Core messaging | 43,200 msgs (≤5KB each → 1 billable unit each) | $1.00 / 1,000,000 messages | $0.0432 |
| IoT Core connectivity | 43,200 connection-minutes | $0.08 / 1,000,000 minutes | $0.0035 |
| IoT Rules Engine | ~2 rule evaluations + ~1 action per channels msg (ingest rule + alert rule, both matching every channels publish) ≈ 129,600 units | $0.15 / 1,000,000 (triggers + actions) | $0.0195 |
| Firehose ingestion | 43,200 records, billed in 5KB increments regardless of actual ~1KB size → 43,200 × 5KB ≈ 0.206GB | $0.029 / GB | $0.0060 |
| Firehose dynamic partitioning (processing) | same 0.206GB processed | $0.020 / GB | $0.0041 |
| Firehose dynamic partitioning (S3 objects delivered) | 900s buffer → 2,880 flushes/month, ~1 object/device/flush | $0.005 / 1,000 objects | $0.0144 |
| S3 storage (Standard, growing over the retention window before the 90d→IA transition) | a few tens of MB accumulated | $0.023 / GB-month | ~$0.003 |
| Events/vibration-summary padding | small, occasional messages/actions not itemized above | — | ~$0.005 (rounded allowance) |
| **Total (computed)** | | | **≈ $0.098/device/month** |
| **Conservative rounded total** | | | **≈ $0.15/device/month** |

That's **well under $1/device/month**, with roughly 40% margin baked into
the rounding before even accounting for the fact that the Rules Engine
and dynamic-partitioning line items above are themselves conservative
(worst-case: every rule match assumed to also fire its action; every
15-minute buffer window assumed to actually have new data, which it will,
given the 1/min publish rate).

The single biggest lever if this needs to go materially lower at scale is
the Firehose dynamic-partitioning "objects delivered" charge (a shared
cost across the whole fleet's flush windows, not truly per-device) —
lengthening the buffer interval trades it for latency, but 900s is
already Firehose's maximum, so the next lever is batching more
devices'/partitions' worth of data per S3 object, which naturally
improves as fleet size grows (see **Scaling**, below).

### Alerting cost note

- **Email (SNS)**: effectively free at this scale — SNS's free tier
  covers far more than a monitoring fleet's worth of threshold alerts,
  and even beyond the free tier, email delivery is priced per 100,000
  notifications, not per-message in any way that matters here. Confirmed
  subscription required once (see bring-up step 5).
- **SMS (SNS, optional, via `var.alert_phone`)**: **not** free-tier
  covered at any meaningful scale — SNS SMS is billed **per message
  sent**, with per-message pricing that varies by destination country
  (US SMS is on the order of a few cents each — verify current per-
  message pricing at
  [aws.amazon.com/sns/sms-pricing](https://aws.amazon.com/sns/sms-pricing/)
  before enabling it broadly). Fine for "this matters enough to wake
  someone up" alerts on a handful of thresholds; would add up fast if
  every routine channels-stream anomaly fanned out to SMS. Left off by
  default (`alert_phone` defaults to `null`).

## Scaling note: what changes at 100 devices

**Nothing structural.** This architecture was deliberately chosen to be
flat with device count:

- **IoT Core / MQTT**: no fleet-size-aware configuration anywhere — the
  device policy scopes each device to its own topic namespace via the
  `iot:Connection.Thing.ThingName` policy variable (see
  `terraform/iot_core.tf`), so adding device #100 is
  `provision-device.sh -n <new-thing-name>`, not a Terraform change.
- **Ingest**: one shared Firehose delivery stream and one shared S3
  bucket already handle arbitrarily many devices — dynamic partitioning
  is what keeps their data separated by `device_id=.../dt=.../` prefix
  without per-device Terraform resources. 100 devices × 43,200 msgs/month
  is still only ~4.3M messages/month total — nowhere near any AWS
  service quota that would force an architecture change.
- **Query**: the Glue table and its partition scheme don't change; Athena
  scans more partitions, not a differently-shaped table.
- **Cost**: scales close to linearly — multiply the per-device total
  above by device count as a first approximation. The one line item that
  scales *better* than linear is Firehose's per-object delivery charge,
  since more devices sharing the same buffer window means more device-
  partitions batched into the *same* flush cycle rather than each device
  forcing its own flush.
- **What would actually force a redesign**: not 100 devices — more like
  10,000+ (approaching IoT Core's per-account connection/throughput
  limits, at which point account-level quota increases or fleet
  provisioning templates become relevant), or a requirement this
  skeleton explicitly doesn't attempt yet (sub-minute live dashboards at
  fleet scale — see the Timestream/Grafana "future" branch in
  [docs/cloud/architecture.md](../docs/cloud/architecture.md)).
