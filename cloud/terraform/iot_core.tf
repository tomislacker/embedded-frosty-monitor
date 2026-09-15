# =============================================================================
# frostsight cloud — IoT Core: thing type and least-privilege device policy
# =============================================================================
#
# What Terraform owns here: the *shape* every device fits into — the thing
# type, and the IAM-like IoT policy every device's certificate is attached
# to. What Terraform explicitly does NOT own: individual things, individual
# X.509 certificates/keys, or per-device policy attachments. Those are
# created per-device by cloud/scripts/provision-device.sh at install time,
# on demand, one technician-run script invocation per unit shipped — not
# declared in advance in a .tf file. Provisioning a fleet of devices through
# `terraform apply` would mean checking device certs/keys into (or awkwardly
# out-of-banding them from) this repo's state, which is worse than just
# letting AWS generate a keypair per device the way create-keys-and-
# certificate is designed for. See cloud/scripts/provision-device.sh.
# =============================================================================

resource "aws_iot_thing_type" "frostsight_monitor" {
  name = "frostsight-monitor"

  properties {
    description = "frosty-monitor field unit: ESP32-S3 logger core publishing aggregated channel/event/vibration-summary JSON over MQTT/TLS. See docs/firmware/connectivity.md and docs/cloud/architecture.md."
  }
}

# -----------------------------------------------------------------------------
# Device IoT policy
# -----------------------------------------------------------------------------
# Least privilege, scoped entirely by the device's own thing name via the
# `iot:Connection.Thing.ThingName` policy variable:
#   - Connect only as a client ID equal to the device's own thing name (so
#     one device's certificate cannot be used to connect as another device
#     and steal its MQTT session).
#   - Publish/Subscribe/Receive only under its own topic namespace,
#     frostsight/<thing_name>/*  — a compromised or cloned device
#     certificate cannot read or write another device's data.
#
# NOTE on the `$${...}` below: this is Terraform string-interpolation
# escaping, not a typo. `${iot:Connection.Thing.ThingName}` is an *AWS IoT
# policy variable*, resolved by IoT Core at connect/publish time — it must
# reach the rendered JSON literally as `${...}`. A single `$` here would
# make Terraform try (and fail) to resolve `iot:Connection.Thing.ThingName`
# as a Terraform expression, so it's written `$$` to produce one literal
# `$` in the output.
# -----------------------------------------------------------------------------

data "aws_iam_policy_document" "device_policy" {
  # --- Connect: only as yourself ---
  statement {
    sid     = "ConnectAsOwnThingName"
    effect  = "Allow"
    actions = ["iot:Connect"]
    resources = [
      "arn:aws:iot:${local.region}:${local.account_id}:client/$${iot:Connection.Thing.ThingName}",
    ]
  }

  # --- Publish: only under your own topic namespace ---
  statement {
    sid     = "PublishOwnTopics"
    effect  = "Allow"
    actions = ["iot:Publish"]
    resources = [
      "arn:aws:iot:${local.region}:${local.account_id}:topic/${local.mqtt_topic_prefix}/$${iot:Connection.Thing.ThingName}/*",
    ]
  }

  # --- Subscribe: only to your own topic filters ---
  statement {
    sid     = "SubscribeOwnTopics"
    effect  = "Allow"
    actions = ["iot:Subscribe"]
    resources = [
      "arn:aws:iot:${local.region}:${local.account_id}:topicfilter/${local.mqtt_topic_prefix}/$${iot:Connection.Thing.ThingName}/*",
    ]
  }

  # --- Receive: only messages actually delivered on your own topics ---
  # (Subscribe and Receive are separate IoT actions; a device that can
  # Subscribe to a filter still needs Receive to get delivered messages.
  # frosty-monitor devices don't currently subscribe to anything — no
  # device-shadow or command-and-control channel exists yet — but this is
  # included so the policy is correct if/when that lands, rather than
  # silently broken.)
  statement {
    sid     = "ReceiveOwnTopics"
    effect  = "Allow"
    actions = ["iot:Receive"]
    resources = [
      "arn:aws:iot:${local.region}:${local.account_id}:topic/${local.mqtt_topic_prefix}/$${iot:Connection.Thing.ThingName}/*",
    ]
  }
}

resource "aws_iot_policy" "device_policy" {
  name   = "${var.name_prefix}-device-policy"
  policy = data.aws_iam_policy_document.device_policy.json
}
