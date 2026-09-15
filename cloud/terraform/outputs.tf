# =============================================================================
# frostsight cloud — outputs
# =============================================================================
# Mostly here so `terraform plan`/`apply` output (once this is ever applied
# for real) and cloud/scripts/provision-device.sh have a stable set of
# names/ARNs to reference, without hardcoding them.
# =============================================================================

output "iot_thing_type_name" {
  description = "IoT thing type every provisioned device is created as. Used by provision-device.sh."
  value       = aws_iot_thing_type.frostsight_monitor.name
}

output "iot_device_policy_name" {
  description = "Least-privilege IoT policy attached to each device's certificate. Used by provision-device.sh."
  value       = aws_iot_policy.device_policy.name
}

output "raw_bucket_name" {
  description = "S3 bucket holding raw channels/ and events/ JSON."
  value       = aws_s3_bucket.raw.bucket
}

output "glue_database_name" {
  description = "Glue Catalog database queryable from Athena."
  value       = aws_glue_catalog_database.frostsight.name
}

output "channels_firehose_stream_name" {
  description = "Kinesis Firehose delivery stream the channels IoT rule feeds."
  value       = aws_kinesis_firehose_delivery_stream.channels.name
}

output "alerts_sns_topic_arn" {
  description = "SNS topic the example alerting rule publishes to."
  value       = aws_sns_topic.alerts.arn
}
