# =============================================================================
# frostsight cloud — shared locals and account/region lookups
# =============================================================================
# `data.aws_caller_identity` and `data.aws_region` exist so ARNs below never
# have an account ID or region hardcoded in this repo — they're resolved at
# plan/apply time from whatever account/credentials are active. This is the
# *only* place account identity enters this configuration.
# =============================================================================

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

locals {
  account_id = data.aws_caller_identity.current.account_id
  region     = data.aws_region.current.name

  # frostsight/<thing_name>/channels|events|vibration — see
  # docs/firmware/connectivity.md (device side, owned by another doc) and
  # docs/cloud/architecture.md (this side) for the topic contract.
  mqtt_topic_prefix = "frostsight"

  common_name = var.name_prefix
}
