# Inputs.
#
# The rule this file exists to enforce: no ARNs, account IDs, or region
# strings scattered through the resource definitions. An ARN written inline in
# five places is five places to miss when one of them changes, and an account
# ID inline is a config that silently targets the wrong account when someone
# assumes a different role.
#
# Everything derivable is derived instead of declared -- account ID and region
# come from data sources in providers.tf, and ARNs are built from resource
# attributes so they follow renames automatically.

variable "aws_region" {
  description = "Region everything lives in. Single-region by design; multi-region is out of scope."
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Name prefix for resources. Changing this does not rename what already exists."
  type        = string
  default     = "quotejar"
}

variable "github_repository" {
  description = <<-EOT
    owner/repo, used in the OIDC trust policy.

    Note this is the *human-readable* form. The trust policy itself matches on
    the immutable numeric IDs AWS actually receives in the `sub` claim -- see
    iam_github.tf, where getting this wrong cost an afternoon in QJ-4.
  EOT
  type        = string
  default     = "cefaust/quotejar"
}

# --- Existing network ------------------------------------------------------
#
# The VPC, its subnets, and its route table predate this config: they are the
# account's default VPC, created by AWS, and are deliberately *not* managed
# here. Adopting a default VPC into Terraform means `terraform destroy` can
# delete the network every other resource sits in, which is a large downside
# for no benefit at this size.
#
# They are referenced by ID instead, which is why these are variables rather
# than resources.

variable "vpc_id" {
  description = "Existing VPC the Lambda, RDS instance, and endpoints sit in."
  type        = string
  default     = "vpc-0a7d500454d8fec5b"
}

variable "route_table_id" {
  description = "Route table the DynamoDB gateway endpoint attaches to."
  type        = string
  default     = "rtb-08a5b21d76235cd7f"
}

# --- Application configuration ---------------------------------------------

variable "lambda_memory_mb" {
  description = "Lambda memory. Also scales CPU, which is why bcrypt timing depends on it."
  type        = number
  default     = 1024
}

variable "lambda_timeout_seconds" {
  description = "Lambda timeout."
  type        = number
  default     = 30
}

variable "lambda_reserved_concurrency" {
  description = <<-EOT
    Reserved concurrency.

    A cost control first and a capacity control second: it makes a runaway
    bill impossible, and it is also the bottleneck documented in the rate
    limiting section of the README. Raising it is a real decision, not a
    tuning knob -- it trades a service-availability ceiling for a billing one.
  EOT
  type        = number
  default     = 5
}

variable "db_instance_class" {
  description = "RDS instance class. Free-tier eligible at db.t4g.micro."
  type        = string
  default     = "db.t4g.micro"
}

variable "db_allocated_storage_gb" {
  description = "RDS storage in GB."
  type        = number
  default     = 20
}
