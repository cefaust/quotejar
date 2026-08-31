# Outputs.
#
# Deliberately few. Every output is also written to state in plaintext and
# printed by `terraform output`, so an output is a small decision about what
# is safe to surface, not a free convenience.
#
# Nothing here is secret: a hostname and a URL. Both are already discoverable
# by anyone who can call the API, and neither grants access on its own -- the
# database is reachable only from inside the VPC (see the security groups in
# network.tf), and the Function URL is public by design, with the JWT layer
# doing the actual authorisation.
#
# What is deliberately NOT output: anything from aws_db_instance.password.
# Marking an output `sensitive = true` only hides it from CLI display -- the
# value still sits in the state JSON in the clear, and `terraform output
# -json` prints it regardless. Sensitivity is a display setting, not a
# security control.

output "function_url" {
  description = "Public HTTPS endpoint for the API."
  value       = aws_lambda_function_url.api.function_url
}

output "rds_endpoint" {
  description = "RDS hostname. Reachable only from inside the VPC, or via a just-in-time security group rule -- see the README runbook."
  value       = aws_db_instance.main.endpoint
}

output "ecr_repository_url" {
  description = "Registry the CD pipeline pushes images to."
  value       = aws_ecr_repository.app.repository_url
}

output "rate_limit_table_name" {
  description = "DynamoDB table backing the rate limiter. Matches settings.rate_limit_table in app/config.py."
  value       = aws_dynamodb_table.rate_limits.name
}
