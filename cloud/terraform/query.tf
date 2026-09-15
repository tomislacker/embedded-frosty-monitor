# =============================================================================
# frostsight cloud — query layer: Glue Catalog database + table over the
# raw channels JSON in S3, queryable directly from Athena.
# =============================================================================
#
# Column names/types below are synced field-by-field against the firmware
# aggregate schema in docs/firmware/connectivity.md (nested stat objects).
# If either side changes, change both in the same commit. Still re-verify
# against captured real payloads at the first Live pilot.
# =============================================================================

resource "aws_glue_catalog_database" "frostsight" {
  name        = var.glue_database_name
  description = "frostsight cloud telemetry — Athena-queryable tables over raw S3 JSON. See docs/cloud/architecture.md."
}

# -----------------------------------------------------------------------------
# channels table
# -----------------------------------------------------------------------------
# One row per per-minute aggregate message on frostsight/<device_id>/channels.
# Partitioned by device_id and dt (date) to match the Firehose dynamic-
# partitioning prefix in ingest.tf: channels/device_id=<x>/dt=<yyyy-mm-dd>/.
#
# Payload shape — SYNCED with the firmware aggregate schema in
# docs/firmware/connectivity.md (nested per-channel stat objects, NOT
# flattened _mean/_min/_max fields). Re-verify against real payloads at the
# first Live pilot before relying on Athena results.
#
#   {
#     "ts_iso": "2026-09-14T12:34:00Z",
#     "ts_unix_ms": 1789475640000,
#     "window_s": 60,
#     "n": 58,
#     "current_beater_a": {"mean": 2.145, "min": 1.980, "max": 2.310},
#     "current_compressor_a": {"mean": 6.402, "min": 0.000, "max": 7.850},
#     "temp_cylinder_c": {"mean": -4.220, "min": -4.500, "max": -3.900},
#     ... one object per populated numeric channel ...
#     "drip_rate_cpm": {"mean": 0.000, "min": 0.000, "max": 0.000},
#     "beater_on": true,
#     "compressor_cmd": true,
#     "tcc_satisfied": true,
#     "hp_ok": true
#   }
#
# Channel names mirror docs/firmware/data-format-spec.md. Channels that are
# all-NaN for a window (unpopulated optional probes: temp_hopper_c,
# moisture_raw, refrigerant_raw) are OMITTED from the payload; they are
# still declared as columns below and the JSON SerDe surfaces them as NULL.
# device_id is NOT in the payload — it comes from the topic and lands in
# the S3 partition path (declared as a partition key below). There is no
# derived short-cycle flag in the payload today; short-cycle detection
# lives in the analysis package (see alerting.tf's comment block).
# -----------------------------------------------------------------------------

resource "aws_glue_catalog_table" "channels" {
  name          = "channels"
  database_name = aws_glue_catalog_database.frostsight.name
  table_type    = "EXTERNAL_TABLE"

  parameters = {
    classification       = "json"
    "has_encrypted_data" = "false"
  }

  storage_descriptor {
    location      = "s3://${aws_s3_bucket.raw.bucket}/channels/"
    input_format  = "org.apache.hadoop.mapred.TextInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.HiveIgnoreKeyTextOutputFormat"

    ser_de_info {
      name                  = "channels-json"
      serialization_library = "org.openx.data.jsonserde.JsonSerDe"
      # `ignore.malformed.json` keeps one bad record from failing an entire
      # Athena scan; anything unparseable also already landed under
      # channels-errors/ via Firehose's own error output (see ingest.tf).
      parameters = {
        "ignore.malformed.json" = "true"
      }
    }

    # A list of {name, type} objects, not a map, specifically so column
    # order in the rendered Glue table follows this file's (meaningful,
    # channel-grouped) order rather than being silently re-sorted
    # alphabetically the way a `for_each` over a map would.
    dynamic "columns" {
      for_each = [
        { name = "ts_iso", type = "string" }, # ISO-8601 UTC; CAST(ts_iso AS timestamp) at query time
        { name = "ts_unix_ms", type = "bigint" },
        { name = "window_s", type = "int" },
        { name = "n", type = "int" }, # rows aggregated into this window

        { name = "current_beater_a", type = "struct<mean:double,min:double,max:double>" },
        { name = "current_compressor_a", type = "struct<mean:double,min:double,max:double>" },
        { name = "temp_cylinder_c", type = "struct<mean:double,min:double,max:double>" },
        { name = "temp_cond_in_c", type = "struct<mean:double,min:double,max:double>" },
        { name = "temp_cond_out_c", type = "struct<mean:double,min:double,max:double>" },
        { name = "temp_ambient_c", type = "struct<mean:double,min:double,max:double>" },
        { name = "temp_hopper_c", type = "struct<mean:double,min:double,max:double>" },
        { name = "temp_discharge_c", type = "struct<mean:double,min:double,max:double>" },
        { name = "drip_rate_cpm", type = "struct<mean:double,min:double,max:double>" },
        { name = "moisture_raw", type = "struct<mean:double,min:double,max:double>" },
        { name = "refrigerant_raw", type = "struct<mean:double,min:double,max:double>" },

        { name = "beater_on", type = "boolean" },
        { name = "compressor_cmd", type = "boolean" },
        { name = "tcc_satisfied", type = "boolean" },
        { name = "hp_ok", type = "boolean" },
      ]

      content {
        name = columns.value.name
        type = columns.value.type
      }
    }
  }

  # Partition keys are derived from the S3 key path (Hive-style
  # device_id=.../dt=.../), not from the JSON body — the payload carries
  # no device_id field; identity comes from the MQTT topic. Run
  # `MSCK REPAIR TABLE channels;` (or an AWS Glue Crawler, not included in
  # this skeleton) after new device_id/dt partitions appear, to register
  # them with the catalog.
  partition_keys {
    name = "device_id"
    type = "string"
  }
  partition_keys {
    name = "dt"
    type = "string"
  }
}
