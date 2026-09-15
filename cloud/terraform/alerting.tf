# =============================================================================
# frostsight cloud — alerting example
# =============================================================================
#
# *** THRESHOLDS ARE PLACEHOLDERS. *** var.drip_rate_alert_threshold_cpm
# (variables.tf) exists so this rule is wired up end-to-end and reviewable,
# not because a threshold has been calibrated against real field data. Per
# docs/roadmap.md item 7, drip-rate alert threshold calibration is an
# explicitly open item. Do not treat the default as a spec value; do not
# point this at a real device fleet's alerts until someone who has looked
# at real drip_rate_cpm distributions signs off on the number.
#
# The aggregate payload (docs/firmware/connectivity.md) carries no derived
# short-cycle flag today — short-cycle detection lives in the analysis
# package's detect_short_cycling(). If a device-side derived flag is added
# later, extend this rule's WHERE clause then (and query.tf in the same
# commit). Until then this rule alerts on drip rate only.
# =============================================================================

resource "aws_sns_topic" "alerts" {
  name = "${var.name_prefix}-alerts"
}

resource "aws_sns_topic_subscription" "alerts_email" {
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.alert_email

  # SNS email subscriptions require the recipient to click a confirmation
  # link sent immediately after `apply` — there is no way to skip that
  # step from Terraform. No alerts arrive until it's confirmed.
}

resource "aws_sns_topic_subscription" "alerts_sms" {
  count = var.alert_phone == null ? 0 : 1

  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "sms"
  endpoint  = var.alert_phone

  # Cost caveat (see cloud/README.md's alerting cost note): unlike email,
  # SNS SMS is billed per message (US SMS is on the order of a few cents
  # each at today's pricing — verify at aws.amazon.com/pricing/sns before
  # relying on this) and is NOT meaningfully covered by any free tier at
  # fleet scale. Reserve this for alerts urgent enough to justify it; the
  # email subscription above is the default channel.
}

# -----------------------------------------------------------------------------
# IoT rule: threshold alert on the per-minute channels stream -> SNS
# -----------------------------------------------------------------------------
# Demonstrates the shape of threshold-based alerting directly in IoT Core's
# SQL rules engine, with no Lambda or other compute in the path: the rule
# both filters (WHERE) and shapes the outbound message (SELECT) in one
# step. This is intentionally a single example rule, not a rules-per-
# failure-signature library — see docs/cloud/architecture.md for why
# real signature detection stays a dashed/future Lambda item rather than
# something hand-rolled in IoT SQL.
# -----------------------------------------------------------------------------

data "aws_iam_policy_document" "iot_rule_alerts_permissions" {
  statement {
    sid       = "PublishToAlertsTopic"
    effect    = "Allow"
    actions   = ["sns:Publish"]
    resources = [aws_sns_topic.alerts.arn]
  }
}

resource "aws_iam_role" "iot_rule_alerts" {
  name               = "${var.name_prefix}-iot-rule-alerts"
  assume_role_policy = data.aws_iam_policy_document.iot_rule_assume_role.json
}

resource "aws_iam_role_policy" "iot_rule_alerts" {
  name   = "${var.name_prefix}-iot-rule-alerts"
  role   = aws_iam_role.iot_rule_alerts.id
  policy = data.aws_iam_policy_document.iot_rule_alerts_permissions.json
}

resource "aws_iot_topic_rule" "drip_rate_alert" {
  name        = "${replace(var.name_prefix, "-", "_")}_drip_rate_alert"
  description = "PLACEHOLDER example alert: high mean drip rate on the per-minute channels stream. Threshold is not calibrated -- see comment block above."
  enabled     = true
  sql_version = "2016-03-23"

  # device_id comes from the topic (frostsight/<device_id>/channels), not
  # the payload; drip_rate_cpm is a nested {mean,min,max} object per the
  # firmware aggregate schema, accessed with dot notation.
  sql = <<-EOT
    SELECT
      topic(2) AS device_id,
      ts_iso,
      drip_rate_cpm.mean AS drip_rate_cpm_mean
    FROM '${local.mqtt_topic_prefix}/+/channels'
    WHERE
      drip_rate_cpm.mean > ${var.drip_rate_alert_threshold_cpm}
  EOT

  sns {
    target_arn = aws_sns_topic.alerts.arn
    role_arn   = aws_iam_role.iot_rule_alerts.arn
    # RAW delivers exactly the SELECTed JSON above as the SNS message body
    # (no extra IoT-rule envelope), so email/SMS subscribers see the
    # device_id/ts/threshold-breaching fields directly.
    message_format = "RAW"
  }
}
