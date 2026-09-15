# =============================================================================
# frostsight cloud — ingest pipeline
#
#   device --MQTT/TLS--> IoT Core --topic rule--> Firehose --> S3 (channels)
#   device --MQTT/TLS--> IoT Core --topic rule--> S3 direct  (events)
#
# See docs/cloud/architecture.md for the full diagram and the reasoning
# behind store-and-forward (SD card is the source of truth; this pipeline
# is best-effort/backfillable, not a durability guarantee).
# =============================================================================

# -----------------------------------------------------------------------------
# Raw landing bucket
# -----------------------------------------------------------------------------
# One bucket, two logical prefixes (channels/, events/), each partitioned by
# device and date so Athena partition pruning works and so a bad/misbehaving
# device is trivially isolable by prefix. Bucket name is derived (prefix +
# account id + region), never a literal — see locals.tf.
# -----------------------------------------------------------------------------

resource "aws_s3_bucket" "raw" {
  bucket = "${var.name_prefix}-raw-${local.account_id}-${local.region}"
}

resource "aws_s3_bucket_public_access_block" "raw" {
  bucket = aws_s3_bucket.raw.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "raw" {
  bucket = aws_s3_bucket.raw.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "aws:kms"
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_versioning" "raw" {
  bucket = aws_s3_bucket.raw.id
  versioning_configuration {
    # Off by default: this is high-volume, low-value-per-object telemetry,
    # not source code. Versioning here mostly just doubles storage cost
    # from accidental overwrites that basically can't happen (every object
    # key already includes a unique timestamp/uuid). Flip to "Enabled" if
    # Ben wants belt-and-suspenders protection against a bad Firehose
    # config overwriting a prefix.
    status = "Disabled"
  }
}

# -----------------------------------------------------------------------------
# Retention / cost hygiene: raw JSON -> Infrequent Access after 90 days.
# -----------------------------------------------------------------------------
# No expiration rule is set — nobody has decided a real retention *ceiling*
# for raw telemetry yet, and given projected volume (see cost model in
# cloud/README.md — a handful of GB/month across the whole fleet), leaving
# it to grow while that decision gets made costs very little. A commented
# starting point for a hard expiration is included below for when that
# decision is made.
# -----------------------------------------------------------------------------

resource "aws_s3_bucket_lifecycle_configuration" "raw" {
  bucket = aws_s3_bucket.raw.id

  rule {
    id     = "channels-ia-after-90d"
    status = "Enabled"
    filter {
      prefix = "channels/"
    }
    transition {
      days          = 90
      storage_class = "STANDARD_IA"
    }
    # abort_incomplete_multipart_upload cleans up any partial multipart
    # uploads (shouldn't really happen for Firehose's own small PUTs, but
    # cheap insurance) so they don't sit around accruing storage charges.
    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }

    # --- Not enabled: pick a real number before uncommenting. ---
    # expiration {
    #   days = 730
    # }
  }

  rule {
    id     = "events-ia-after-90d"
    status = "Enabled"
    filter {
      prefix = "events/"
    }
    transition {
      days          = 90
      storage_class = "STANDARD_IA"
    }
    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }

  rule {
    id     = "errors-ia-after-90d"
    status = "Enabled"
    filter {
      prefix = "channels-errors/"
    }
    transition {
      days          = 90
      storage_class = "STANDARD_IA"
    }
    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }
}

# =============================================================================
# Channels ingest: IoT rule -> Kinesis Data Firehose -> S3
# =============================================================================
# Why Firehose for channels and not for events (see below): channels is the
# steady, predictable ~1 msg/min/device stream, and Firehose's whole job —
# buffer many small records and batch them into fewer, larger S3 objects —
# is exactly what a fleet of devices each sending a ~1KB message a minute
# needs to avoid the classic "millions of tiny S3 objects" problem. The
# buffering delay Firehose adds (minutes) is irrelevant for a stream that's
# already a 1-minute rollup, not a real-time feed.
# =============================================================================

resource "aws_cloudwatch_log_group" "firehose_channels" {
  name              = "/aws/kinesisfirehose/${var.name_prefix}-channels"
  retention_in_days = 30
}

data "aws_iam_policy_document" "firehose_assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["firehose.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "firehose_channels" {
  name               = "${var.name_prefix}-firehose-channels"
  assume_role_policy = data.aws_iam_policy_document.firehose_assume_role.json
}

data "aws_iam_policy_document" "firehose_channels_permissions" {
  statement {
    sid    = "WriteRawBucket"
    effect = "Allow"
    actions = [
      "s3:AbortMultipartUpload",
      "s3:GetBucketLocation",
      "s3:GetObject",
      "s3:ListBucket",
      "s3:ListBucketMultipartUploads",
      "s3:PutObject",
    ]
    resources = [
      aws_s3_bucket.raw.arn,
      "${aws_s3_bucket.raw.arn}/*",
    ]
  }

  statement {
    sid    = "WriteDeliveryLogs"
    effect = "Allow"
    actions = [
      "logs:PutLogEvents",
    ]
    resources = [
      "${aws_cloudwatch_log_group.firehose_channels.arn}:*",
    ]
  }
}

resource "aws_iam_role_policy" "firehose_channels" {
  name   = "${var.name_prefix}-firehose-channels"
  role   = aws_iam_role.firehose_channels.id
  policy = data.aws_iam_policy_document.firehose_channels_permissions.json
}

resource "aws_kinesis_firehose_delivery_stream" "channels" {
  name        = "${var.name_prefix}-channels"
  destination = "extended_s3"

  extended_s3_configuration {
    role_arn   = aws_iam_role.firehose_channels.arn
    bucket_arn = aws_s3_bucket.raw.arn

    # Dynamic partitioning pulls device_id out of each JSON record (via the
    # jq-based MetadataExtraction processor below) so objects land already
    # partitioned by device *and* date without a downstream ETL/Glue job.
    # !{timestamp:...} is Firehose's own delivery-time partition, not
    # something pulled from the record.
    prefix              = "channels/device_id=!{partitionKeyFromQuery:device_id}/dt=!{timestamp:yyyy-MM-dd}/"
    error_output_prefix = "channels-errors/!{firehose:error-output-type}/dt=!{timestamp:yyyy-MM-dd}/"

    # Tuned for tiny volume: one ~1KB message/minute/device means even a
    # 100-device fleet is only ~100KB/min (~1.7KB/s) of input — nowhere
    # near the 5MB buffering_size threshold, so in practice every flush is
    # interval-driven, not size-driven. With dynamic partitioning enabled,
    # Firehose bills per S3 object *delivered* ($0.005/1,000 objects, on
    # top of the per-GB ingestion charge — see cloud/README.md's cost
    # model), and one object is written per active device+date partition
    # per flush. Buffering at the 900s ceiling (Firehose's maximum, not an
    # arbitrary choice) instead of a shorter interval directly cuts that
    # per-device object-delivery cost by 3x versus a 300s buffer, for a
    # trade of a few extra minutes of S3-visibility latency on data that's
    # already a 1-minute rollup — an easy trade for this workload. 5MB is
    # the buffering_size ceiling that would matter if per-device volume
    # ever grew a lot; at today's volume it never triggers a flush on its
    # own.
    buffering_size     = 5
    buffering_interval = 900

    compression_format = "GZIP"

    dynamic_partitioning_configuration {
      enabled = true
    }

    processing_configuration {
      enabled = true

      processors {
        type = "MetadataExtraction"

        parameters {
          parameter_name  = "MetadataExtractionQuery"
          parameter_value = "{device_id:.device_id}"
        }
        parameters {
          parameter_name  = "JsonParsingEngine"
          parameter_value = "JQ-1.0"
        }
      }
    }

    cloudwatch_logging_options {
      enabled         = true
      log_group_name  = aws_cloudwatch_log_group.firehose_channels.name
      log_stream_name = "S3Delivery"
    }
  }
}

# -----------------------------------------------------------------------------
# IoT rule: frostsight/+/channels -> Firehose
# -----------------------------------------------------------------------------

data "aws_iam_policy_document" "iot_rule_assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["iot.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "iot_rule_channels" {
  name               = "${var.name_prefix}-iot-rule-channels"
  assume_role_policy = data.aws_iam_policy_document.iot_rule_assume_role.json
}

data "aws_iam_policy_document" "iot_rule_channels_permissions" {
  statement {
    sid       = "PutRecordsToFirehose"
    effect    = "Allow"
    actions   = ["firehose:PutRecord", "firehose:PutRecordBatch"]
    resources = [aws_kinesis_firehose_delivery_stream.channels.arn]
  }
}

resource "aws_iam_role_policy" "iot_rule_channels" {
  name   = "${var.name_prefix}-iot-rule-channels"
  role   = aws_iam_role.iot_rule_channels.id
  policy = data.aws_iam_policy_document.iot_rule_channels_permissions.json
}

resource "aws_iot_topic_rule" "channels" {
  name        = "${replace(var.name_prefix, "-", "_")}_channels_to_firehose"
  description = "Per-minute aggregated channel JSON -> Firehose -> S3. Field names below are PROVISIONAL, see query.tf."
  enabled     = true
  sql         = "SELECT * FROM '${local.mqtt_topic_prefix}/+/channels'"
  sql_version = "2016-03-23"

  firehose {
    delivery_stream_name = aws_kinesis_firehose_delivery_stream.channels.name
    role_arn             = aws_iam_role.iot_rule_channels.arn
    # One JSON object per Firehose record; Firehose/S3 concatenates
    # records back-to-back in each batched object, so a trailing newline
    # per record keeps the resulting S3 objects valid JSON-Lines for
    # Athena/Glue's JSON SerDe to read one row per line.
    separator = "\n"
  }
}

# =============================================================================
# Events ingest: IoT rule -> S3, direct (no Firehose)
# =============================================================================
# Why direct-to-S3 instead of routing events through the same Firehose (or a
# second one): events are small, occasional, and per docs/firmware's design
# already arrive as complete, immediately-flushable one-off messages (button
# press / system / trigger / error) — there's no steady-rate stream here for
# Firehose's batching to help with, and event volume is low enough that
# "one S3 object per event" is not a small-files problem worth avoiding.
# Skipping Firehose for this stream removes an IAM role, a delivery stream,
# and a CloudWatch log group for no loss of capability. If event volume
# later grows enough that S3 request costs/rate matter, this is the rule to
# revisit — not before.
# =============================================================================

resource "aws_iam_role" "iot_rule_events" {
  name               = "${var.name_prefix}-iot-rule-events"
  assume_role_policy = data.aws_iam_policy_document.iot_rule_assume_role.json
}

data "aws_iam_policy_document" "iot_rule_events_permissions" {
  statement {
    sid       = "PutEventsToRawBucket"
    effect    = "Allow"
    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.raw.arn}/events/*"]
  }
}

resource "aws_iam_role_policy" "iot_rule_events" {
  name   = "${var.name_prefix}-iot-rule-events"
  role   = aws_iam_role.iot_rule_events.id
  policy = data.aws_iam_policy_document.iot_rule_events_permissions.json
}

resource "aws_iot_topic_rule" "events" {
  name        = "${replace(var.name_prefix, "-", "_")}_events_to_s3"
  description = "Immediate small event messages -> S3 directly, one object per event."
  enabled     = true
  sql         = "SELECT *, topic(2) AS device_id FROM '${local.mqtt_topic_prefix}/+/events'"
  sql_version = "2016-03-23"

  s3 {
    bucket_name = aws_s3_bucket.raw.bucket
    role_arn    = aws_iam_role.iot_rule_events.arn
    # $${...} here is escaped Terraform interpolation producing a literal
    # IoT SQL substitution template, same reasoning as iot_core.tf:
    # topic(2) is the device_id segment of frostsight/<device_id>/events,
    # and timestamp() is the rule-evaluation time in epoch millis, used
    # here only to keep keys unique — it is NOT a substitute for the
    # in-payload event timestamp the device sends.
    key = "events/device_id=$${topic(2)}/dt=$${parse_time(\"yyyy-MM-dd\", timestamp())}/$${timestamp()}-$${newuuid()}.json"
  }
}

# NOTE: no rule is defined here for frostsight/+/vibration. Per the
# connectivity contract, that topic carries only occasional small vibration
# *summary* messages — raw burst binaries never leave the SD card (see
# docs/cloud/architecture.md, "what real-time means here"). Wiring up
# ingest for it is a small follow-on (same shape as the events rule above)
# once docs/firmware/connectivity.md nails down that payload's schema; not
# included here to avoid guessing at a schema that isn't written yet.
