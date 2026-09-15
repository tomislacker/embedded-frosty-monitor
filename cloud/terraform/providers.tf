# =============================================================================
# frostsight cloud — provider and Terraform settings
# =============================================================================
#
# STATUS: SKELETON. This has never been applied against a real AWS account.
# See cloud/README.md for the full status banner and bring-up steps.
#
# There is deliberately NO `backend` block below. Local state is fine for
# `terraform validate`/`fmt`/review; the first person to actually `apply`
# this should choose a state backend (S3 + DynamoDB lock table is the usual
# answer) deliberately, not inherit whatever a skeleton happened to ship
# with. Do not add one here as a drive-by change.
# =============================================================================

terraform {
  required_version = ">= 1.5.0, < 2.0.0"

  required_providers {
    aws = {
      source = "hashicorp/aws"
      # Pinned to a major version range only — re-pin to an exact version
      # (or a lockfile-enforced range) before the first real apply. Verify
      # the current 5.x release at registry.terraform.io/providers/hashicorp/aws.
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.region

  # Every resource this skeleton creates gets tagged so it's obvious, in the
  # AWS console or a cost report, that it belongs to this project and was
  # not hand-created.
  default_tags {
    tags = {
      Project     = "frostsight"
      Component   = "cloud-ingest"
      ManagedBy   = "terraform"
      Environment = "skeleton-not-yet-deployed"
    }
  }
}
