# =============================================================================
# frostsight cloud — input variables
# =============================================================================
# Deliberately no account IDs, bucket names with account numbers baked in, or
# other account-specific literals anywhere in this skeleton. Everything that
# varies between "someone's sandbox account" and "the real account this
# eventually runs in" is a variable here, with a placeholder-obvious default
# or no default at all.
# =============================================================================

variable "region" {
  description = <<-EOT
    AWS region to deploy the frostsight ingest stack into. IoT Core, the
    Firehose delivery streams, and the S3/Glue/Athena resources all land in
    this one region — there is no multi-region replication in this
    skeleton. us-east-1 is the default only because it's the most commonly
    available region for every service used here (IoT Core, Kinesis
    Firehose, Glue); it is not a hard requirement.
  EOT
  type        = string
  default     = "us-east-1"
}

variable "name_prefix" {
  description = <<-EOT
    Short prefix applied to every named resource (IoT thing type, IoT
    policy, S3 bucket, Firehose stream, Glue database, SNS topic, etc.) so
    this stack can coexist with other things in the same account and so a
    second environment (e.g. "frostsight-dev" vs "frostsight-prod") can be
    stood up by changing one value. Keep it short and DNS/S3-bucket-name
    safe: lowercase letters, digits, hyphens.
  EOT
  type        = string
  default     = "frostsight"

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{1,30}$", var.name_prefix))
    error_message = "name_prefix must be lowercase alphanumeric/hyphen, start with a letter, and be short enough to leave room for S3 bucket-name suffixes (<= ~30 chars)."
  }
}

variable "alert_email" {
  description = <<-EOT
    Email address subscribed to the SNS alert topic (see alerting.tf). SNS
    email subscriptions require manual confirmation — after the first
    `apply`, the address here gets a "Subscription confirmation" email that
    has to be clicked before alerts actually arrive. There is no sane
    default for this; it must be supplied.
  EOT
  type        = string

  validation {
    condition     = can(regex("^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$", var.alert_email))
    error_message = "alert_email must look like an email address."
  }
}

variable "alert_phone" {
  description = <<-EOT
    Optional E.164 phone number (e.g. "+15555551234") for an SNS SMS
    subscription, for alerts urgent enough to justify per-message SMS cost
    (see the cost note in cloud/README.md — unlike the email subscription,
    SMS is not effectively free). Leave as null to skip SMS entirely; only
    the email subscription is created by default.
  EOT
  type        = string
  default     = null

  validation {
    condition     = var.alert_phone == null || can(regex("^\\+[1-9][0-9]{6,14}$", var.alert_phone))
    error_message = "alert_phone must be E.164 format (e.g. +15555551234) or left as null."
  }
}

# -----------------------------------------------------------------------------
# Alerting thresholds — PLACEHOLDERS. See alerting.tf for the full caveat.
# These numbers are not derived from field data; they exist so the alerting
# example is wired end-to-end and reviewable, not because anyone has decided
# a drip rate above this value means a failing seal. Do not treat a default
# here as a calibrated spec value — cross-check against
# docs/roadmap.md#7-leak-sensing-bench-validation--threshold-tuning, which
# explicitly calls drip-rate threshold calibration an open item.
# -----------------------------------------------------------------------------

variable "drip_rate_alert_threshold_cpm" {
  description = <<-EOT
    PLACEHOLDER threshold, drops/minute, above which the example alerting
    rule fires on a per-minute channels message's drip_rate_cpm_mean. Not
    calibrated against field data — see docs/roadmap.md item 7. Revisit
    once real seal-wear vs. normal-cleaning drip data exists.
  EOT
  type        = number
  default     = 5.0
}

variable "glue_database_name" {
  description = "Name of the Glue Catalog database that holds the Athena-queryable tables over the raw S3 JSON. Kept as its own variable (rather than derived only from name_prefix) so it can be pointed at an existing database if one already exists in the account."
  type        = string
  default     = "frostsight"
}
