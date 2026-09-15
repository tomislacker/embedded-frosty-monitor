#!/usr/bin/env bash
#
# provision-device.sh — create one frostsight IoT Core identity: a Thing, a
# unique X.509 certificate/key pair, and the policy attachment that lets
# that one device connect and publish/subscribe under its own topic
# namespace only (see cloud/terraform/iot_core.tf for the policy itself).
#
# STATUS: part of a SKELETON that has never been run against a real AWS
# account. Read it, understand every `aws iot` call it makes, and run it
# against a real (probably sandbox-first) account deliberately — not as a
# leap of faith. See cloud/README.md for the full bring-up sequence this
# script fits into.
#
# Per-device certs/keys are intentionally NOT created by Terraform (see the
# comment at the top of cloud/terraform/iot_core.tf) — this script is the
# one-command-per-device alternative, meant to be run once per physical
# unit at provisioning time, typically right before the SD card for that
# unit is prepared.
#
# Usage:
#   provision-device.sh -n THING_NAME [-o OUTPUT_DIR] [-p POLICY_NAME]
#                        [-t THING_TYPE] [-r REGION] [-e ENDPOINT_TYPE]
#
#   -n THING_NAME     Required. Device identity, e.g. "delta117a-001"
#                      (site-machine naming convention — see
#                      docs/cloud/architecture.md "multi-tenancy / fleet
#                      view"). Becomes the IoT thing name, the MQTT client
#                      ID, and the topic-namespace segment in
#                      frostsight/<THING_NAME>/*.
#   -o OUTPUT_DIR     Where to write the cert bundle. Default:
#                      ./provisioned/<THING_NAME>
#   -p POLICY_NAME    IoT policy to attach. Default: frostsight-device-policy
#                      (matches the default name_prefix in
#                      cloud/terraform/variables.tf — override if
#                      name_prefix was changed at apply time).
#   -t THING_TYPE     IoT thing type. Default: frostsight-monitor (matches
#                      cloud/terraform/iot_core.tf).
#   -r REGION         AWS region. Default: value of AWS_REGION/AWS_DEFAULT_REGION,
#                      or whatever the active AWS CLI profile/config resolves to.
#   -e ENDPOINT_TYPE  IoT data endpoint type. Default: iot:Data-ATS (the
#                      current recommended endpoint type; the legacy
#                      non-ATS endpoint type is deprecated by AWS and
#                      should not be used for new devices).
#
# Requires: aws-cli v2, jq, curl. Assumes AWS credentials are already
# configured (env vars, profile, SSO, etc.) with permission to call
# iot:CreateThing, iot:CreateKeysAndCertificate, iot:AttachPolicy,
# iot:AttachThingPrincipal, iot:DescribeEndpoint, iot:DescribeThing.
#
# =============================================================================
# IDEMPOTENCE NOTES — read before re-running this for a THING_NAME you've
# already provisioned:
#
#   - `aws iot create-thing` is itself idempotent: calling it again for the
#     same THING_NAME/THING_TYPE is a no-op success, not an error. This
#     script relies on that and does not pre-check thing existence.
#
#   - `aws iot create-keys-and-certificate` is NOT idempotent — it mints a
#     brand-new certificate and private key on every single call, no
#     matter what. There is no "get me the existing cert for this thing"
#     API; AWS IoT never re-exposes a private key after the one response
#     that created it. Consequences:
#       * Re-running this script for a THING_NAME that's already
#         provisioned creates a SECOND, independent, fully-active
#         certificate attached to the same thing and policy — it does not
#         replace or rotate the first one. Both certs work.
#       * If that's not what you want (typical case: you lost the output
#         dir, or a device's card was replaced), deprovision the OLD
#         certificate deliberately after confirming the new one works —
#         see deprovision-device.sh — rather than leaving orphaned active
#         certificates attached to the thing indefinitely.
#       * This script always prints the new certificate ARN so you can
#         track which cert is "the current one" outside of AWS if needed.
#
#   - This script is safe to Ctrl-C and re-run: everything up through
#     thing creation is idempotent, and if it dies after minting a
#     certificate but before finishing, re-running mints a fresh
#     certificate (see above) rather than reusing the half-written one —
#     there is no partial-cert resume path, by design, since a
#     certificate's private key is only ever available in that one API
#     response.
# =============================================================================

set -euo pipefail

# ---- defaults ---------------------------------------------------------------
THING_NAME=""
OUTPUT_DIR=""
POLICY_NAME="frostsight-device-policy"
THING_TYPE="frostsight-monitor"
REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-}}"
ENDPOINT_TYPE="iot:Data-ATS"
AMAZON_ROOT_CA1_URL="https://www.amazontrust.com/repository/AmazonRootCA1.pem"

usage() {
  # Usage text duplicated from the header comment on purpose — this is what
  # a technician actually sees at the terminal.
  grep -E '^#( |$)' "$0" | sed -n '/^# Usage:/,/^# Requires:/p' | sed 's/^# \{0,1\}//'
  exit 1
}

log()  { printf '[provision-device] %s\n' "$*" >&2; }
die()  { printf '[provision-device] ERROR: %s\n' "$*" >&2; exit 1; }

while getopts ":n:o:p:t:r:e:h" opt; do
  case "$opt" in
    n) THING_NAME="$OPTARG" ;;
    o) OUTPUT_DIR="$OPTARG" ;;
    p) POLICY_NAME="$OPTARG" ;;
    t) THING_TYPE="$OPTARG" ;;
    r) REGION="$OPTARG" ;;
    e) ENDPOINT_TYPE="$OPTARG" ;;
    h) usage ;;
    \?) die "Unknown option: -$OPTARG" ;;
    :) die "Option -$OPTARG requires an argument" ;;
  esac
done

[[ -n "$THING_NAME" ]] || { log "Missing required -n THING_NAME"; usage; }

# site-machine naming convention (see docs/cloud/architecture.md); enforced
# loosely here (DNS/topic-safe characters only) rather than to the letter,
# since the convention is a recommendation, not an API constraint.
if [[ ! "$THING_NAME" =~ ^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$ ]]; then
  die "THING_NAME '$THING_NAME' should be alphanumeric plus '-'/'_' (AWS IoT thing-name-safe), <=128 chars"
fi

OUTPUT_DIR="${OUTPUT_DIR:-./provisioned/${THING_NAME}}"
CERTS_DIR="${OUTPUT_DIR}/certs"

REGION_ARGS=()
if [[ -n "$REGION" ]]; then
  REGION_ARGS=(--region "$REGION")
fi

# ---- preflight ----------------------------------------------------------

for bin in aws jq curl; do
  command -v "$bin" >/dev/null 2>&1 || die "'$bin' is required but not found on PATH"
done

aws sts get-caller-identity "${REGION_ARGS[@]}" >/dev/null \
  || die "AWS credentials not usable (check env/profile/SSO login) — see 'aws sts get-caller-identity'"

aws iot describe-thing-type --thing-type-name "$THING_TYPE" "${REGION_ARGS[@]}" >/dev/null 2>&1 \
  || die "Thing type '$THING_TYPE' does not exist in this account/region — apply cloud/terraform first (see cloud/README.md)"

aws iot get-policy --policy-name "$POLICY_NAME" "${REGION_ARGS[@]}" >/dev/null 2>&1 \
  || die "IoT policy '$POLICY_NAME' does not exist in this account/region — apply cloud/terraform first (see cloud/README.md)"

if [[ -e "$OUTPUT_DIR" ]]; then
  die "Output dir '$OUTPUT_DIR' already exists — remove it or pass a different -o to avoid overwriting a previous provisioning record"
fi

# ---- thing ----------------------------------------------------------------

log "Creating (or confirming) thing '$THING_NAME' of type '$THING_TYPE'..."
aws iot create-thing \
  --thing-name "$THING_NAME" \
  --thing-type-name "$THING_TYPE" \
  "${REGION_ARGS[@]}" \
  >/dev/null
log "Thing OK."

# ---- certificate ------------------------------------------------------------
# NOT idempotent — see the IDEMPOTENCE NOTES block above. This is the one
# and only moment the private key is ever available; it never comes back
# from any subsequent API call.

log "Creating a new certificate/key pair (this cannot be retrieved again later)..."
CERT_JSON="$(aws iot create-keys-and-certificate --set-as-active "${REGION_ARGS[@]}")"

CERT_ARN="$(jq -r '.certificateArn' <<<"$CERT_JSON")"
CERT_PEM="$(jq -r '.certificatePem' <<<"$CERT_JSON")"
PRIVATE_KEY="$(jq -r '.keyPair.PrivateKey' <<<"$CERT_JSON")"

[[ -n "$CERT_ARN" && "$CERT_ARN" != "null" ]] || die "Failed to parse certificateArn from create-keys-and-certificate response"

log "Certificate created: $CERT_ARN"

# ---- attach policy + thing --------------------------------------------------

log "Attaching policy '$POLICY_NAME' to certificate..."
aws iot attach-policy \
  --policy-name "$POLICY_NAME" \
  --target "$CERT_ARN" \
  "${REGION_ARGS[@]}"

log "Attaching certificate to thing '$THING_NAME'..."
aws iot attach-thing-principal \
  --thing-name "$THING_NAME" \
  --principal "$CERT_ARN" \
  "${REGION_ARGS[@]}"

# ---- endpoint ---------------------------------------------------------------

log "Looking up account IoT data endpoint ($ENDPOINT_TYPE)..."
ENDPOINT="$(aws iot describe-endpoint --endpoint-type "$ENDPOINT_TYPE" "${REGION_ARGS[@]}" --query endpointAddress --output text)"
[[ -n "$ENDPOINT" && "$ENDPOINT" != "None" ]] || die "Failed to resolve IoT data endpoint"

# ---- write bundle -------------------------------------------------------

mkdir -p "$CERTS_DIR"
chmod 700 "$OUTPUT_DIR" "$CERTS_DIR"

log "Fetching Amazon Root CA 1..."
if ! curl -fsSL "$AMAZON_ROOT_CA1_URL" -o "${CERTS_DIR}/ca.pem"; then
  die "Failed to download Amazon Root CA 1 from $AMAZON_ROOT_CA1_URL — no network, or the URL moved. Fetch it manually (see https://docs.aws.amazon.com/iot/latest/developerguide/server-authentication.html) and place it at ${CERTS_DIR}/ca.pem before using this bundle."
fi

printf '%s' "$CERT_PEM" > "${CERTS_DIR}/device.pem"
printf '%s' "$PRIVATE_KEY" > "${CERTS_DIR}/device.key"
chmod 600 "${CERTS_DIR}/device.pem" "${CERTS_DIR}/device.key" "${CERTS_DIR}/ca.pem"

# A provisioning record for fleet bookkeeping — deliberately kept OUTSIDE
# certs/ so a naive `cp -r certs/* /Volumes/SDCARD/certs/` never copies
# account/ARN metadata onto the device card, only the three files the
# firmware actually needs.
PROVISIONED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
jq -n \
  --arg thing_name "$THING_NAME" \
  --arg thing_type "$THING_TYPE" \
  --arg policy_name "$POLICY_NAME" \
  --arg cert_arn "$CERT_ARN" \
  --arg endpoint "$ENDPOINT" \
  --arg endpoint_type "$ENDPOINT_TYPE" \
  --arg provisioned_at "$PROVISIONED_AT" \
  '{
     thing_name: $thing_name,
     thing_type: $thing_type,
     policy_name: $policy_name,
     certificate_arn: $cert_arn,
     iot_data_endpoint: $endpoint,
     iot_data_endpoint_type: $endpoint_type,
     provisioned_at_utc: $provisioned_at
   }' > "${OUTPUT_DIR}/provisioning-record.json"

log "Done."
log ""
log "Thing name:        $THING_NAME"
log "Certificate ARN:   $CERT_ARN"
log "IoT data endpoint: $ENDPOINT"
log ""
log "Cert bundle for the SD card (copy the CONTENTS of this dir to the"
log "device card's /certs/ directory, not the dir itself):"
log "  ${CERTS_DIR}/ca.pem"
log "  ${CERTS_DIR}/device.pem"
log "  ${CERTS_DIR}/device.key"
log ""
log "Provisioning record (fleet bookkeeping, NOT for the SD card):"
log "  ${OUTPUT_DIR}/provisioning-record.json"
log ""
log "Point the device's config.json / firmware MQTT config at:"
log "  endpoint: ${ENDPOINT}"
log "  client_id / thing_name: ${THING_NAME}"
log "  topics: frostsight/${THING_NAME}/channels, .../events, .../vibration"
