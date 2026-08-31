# Rate-limit counters (QJ-6).
#
# PAY_PER_REQUEST rather than provisioned: traffic is bursty and near zero at
# rest, so provisioned capacity would mean paying for a floor that is almost
# never used while still throttling during the burst it exists to survive.
#
# TTL on `expires_at` reclaims old counters for free. It is housekeeping, not
# correctness -- deletion is best-effort and can lag 48 hours, which is why
# window expiry is computed from the timestamp in the key instead. See
# app/ratelimit.py.
#
# This is the table the rebuild proof destroys and recreates: it holds only
# ephemeral counters, so losing it costs nothing but a brief window where the
# limiter fails open.

resource "aws_dynamodb_table" "rate_limits" {
  billing_mode                = "PAY_PER_REQUEST"
  deletion_protection_enabled = false
  hash_key                    = "pk"
  name                        = "quotejar-rate-limits"
  range_key                   = null
  read_capacity               = 0
  restore_backup_arn          = null
  restore_date_time           = null
  restore_source_name         = null
  restore_source_table_arn    = null
  restore_to_latest_time      = null
  stream_enabled              = false
  table_class                 = "STANDARD"
  tags                        = {}
  tags_all                    = {}
  write_capacity              = 0
  attribute {
    name = "pk"
    type = "S"
  }
  point_in_time_recovery {
    enabled = false
  }
  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }
}
