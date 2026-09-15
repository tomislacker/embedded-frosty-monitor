#!/usr/bin/env bash
#
# deprovision-device.sh — reverse of provision-device.sh: detach and
# deactivate every certificate attached to a thing, then delete the thing
# itself. Intended for decommissioning a unit, or for cleaning up a
# duplicate certificate created by re-running provision-device.sh (see the
# IDEMPOTENCE NOTES in that script).
#
# STATUS: part of a SKELETON that has never been run against a real AWS
# account. This script is DESTRUCTIVE (deletes IoT certificates and the
# thing record) — read it before running it, and use -y only once you're
# sure. There is no way to recover a deleted certificate's private key
# regardless (AWS IoT never re-exposes it, deleted or not), so the
# practical loss here is the thing/certificate *registration*, not
# anything recoverable from AWS either way.
#
# Usage:
#   deprovision-device.sh -n THING_NAME [-r REGION] [-y] [--keep-thing]
#
#   -n THING_NAME   Required. Same thing name passed to provision-device.sh.
#   -r REGION       AWS region. Default: AWS_REGION/AWS_DEFAULT_REGION or CLI config.
#   -y              Skip the interactive confirmation prompt (for scripting).
#   --keep-thing    Detach/deactivate/delete all certificates but leave the
#                   IoT thing record itself in place. Useful when
#                   replacing a device's certificate (e.g. cleaning up
#                   after an accidental double-provision) without losing
#                   the thing's registry entry, thing-group memberships,
#                   etc.
#
# What this does NOT do: it does not touch anything in
# cloud/terraform/ (the thing type or the shared device policy survive —
# they're shared across the whole fleet, not per-device) and it does not
# touch S3/Firehose/Glue data already ingested from this device.
#
# Manual-steps alternative: if you'd rather not run this script, the
# equivalent by hand is:
#   1. aws iot list-thing-principals --thing-name THING_NAME
#   2. For each returned certificate ARN:
#      a. aws iot list-attached-policies --target CERT_ARN
#      b. aws iot detach-policy --policy-name POLICY --target CERT_ARN  (for each)
#      c. aws iot detach-thing-principal --thing-name THING_NAME --principal CERT_ARN
#      d. aws iot update-certificate --certificate-id CERT_ID --new-status INACTIVE
#      e. aws iot delete-certificate --certificate-id CERT_ID
#   3. aws iot delete-thing --thing-name THING_NAME
#
set -euo pipefail

THING_NAME=""
REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-}}"
ASSUME_YES=0
KEEP_THING=0

log() { printf '[deprovision-device] %s\n' "$*" >&2; }
die() { printf '[deprovision-device] ERROR: %s\n' "$*" >&2; exit 1; }

usage() {
  grep -E '^#( |$)' "$0" | sed -n '/^# Usage:/,/^# What this does NOT do:/p' | sed 's/^# \{0,1\}//'
  exit 1
}

# getopts doesn't natively do long options; handle --keep-thing by hand
# alongside short-opt getopts for everything else.
ARGS=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --keep-thing) KEEP_THING=1; shift ;;
    --) shift; ARGS+=("$@"); break ;;
    *) ARGS+=("$1"); shift ;;
  esac
done
set -- "${ARGS[@]}"

while getopts ":n:r:yh" opt; do
  case "$opt" in
    n) THING_NAME="$OPTARG" ;;
    r) REGION="$OPTARG" ;;
    y) ASSUME_YES=1 ;;
    h) usage ;;
    \?) die "Unknown option: -$OPTARG" ;;
    :) die "Option -$OPTARG requires an argument" ;;
  esac
done

[[ -n "$THING_NAME" ]] || { log "Missing required -n THING_NAME"; usage; }

REGION_ARGS=()
if [[ -n "$REGION" ]]; then
  REGION_ARGS=(--region "$REGION")
fi

command -v aws >/dev/null 2>&1 || die "'aws' is required but not found on PATH"
command -v jq  >/dev/null 2>&1 || die "'jq' is required but not found on PATH"

if ! aws iot describe-thing --thing-name "$THING_NAME" "${REGION_ARGS[@]}" >/dev/null 2>&1; then
  log "Thing '$THING_NAME' does not exist — nothing to do (idempotent no-op)."
  exit 0
fi

if [[ "$ASSUME_YES" -ne 1 ]]; then
  read -r -p "[deprovision-device] Deactivate/delete all certificates for '${THING_NAME}'$( [[ $KEEP_THING -eq 1 ]] || echo " and delete the thing itself" )? [y/N] " reply
  [[ "$reply" =~ ^[Yy]$ ]] || die "Aborted."
fi

PRINCIPALS_JSON="$(aws iot list-thing-principals --thing-name "$THING_NAME" "${REGION_ARGS[@]}" --output json)"
mapfile -t PRINCIPAL_ARNS < <(jq -r '.principals[]' <<<"$PRINCIPALS_JSON")

if [[ "${#PRINCIPAL_ARNS[@]}" -eq 0 ]]; then
  log "No certificates attached to '$THING_NAME'."
fi

for CERT_ARN in "${PRINCIPAL_ARNS[@]}"; do
  CERT_ID="${CERT_ARN##*/}"
  log "Processing certificate $CERT_ID..."

  POLICIES_JSON="$(aws iot list-attached-policies --target "$CERT_ARN" "${REGION_ARGS[@]}" --output json)"
  mapfile -t POLICY_NAMES < <(jq -r '.policies[].policyName' <<<"$POLICIES_JSON")

  for POLICY_NAME in "${POLICY_NAMES[@]}"; do
    log "  Detaching policy '$POLICY_NAME'..."
    aws iot detach-policy --policy-name "$POLICY_NAME" --target "$CERT_ARN" "${REGION_ARGS[@]}"
  done

  log "  Detaching certificate from thing..."
  aws iot detach-thing-principal --thing-name "$THING_NAME" --principal "$CERT_ARN" "${REGION_ARGS[@]}"

  log "  Deactivating certificate..."
  aws iot update-certificate --certificate-id "$CERT_ID" --new-status INACTIVE "${REGION_ARGS[@]}"

  log "  Deleting certificate..."
  aws iot delete-certificate --certificate-id "$CERT_ID" "${REGION_ARGS[@]}"
done

if [[ "$KEEP_THING" -eq 1 ]]; then
  log "Done. Thing '$THING_NAME' left in place (--keep-thing); all certificates detached/deleted."
else
  log "Deleting thing '$THING_NAME'..."
  aws iot delete-thing --thing-name "$THING_NAME" "${REGION_ARGS[@]}"
  log "Done. Thing and all of its certificates are gone."
fi

log ""
log "Not touched by this script: the shared IoT thing type and device"
log "policy (cloud/terraform), and any data already ingested from this"
log "device into S3/Firehose/Glue."
