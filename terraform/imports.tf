# Adoption of resources that already exist and are serving live traffic.
#
# ## Why import blocks rather than `terraform import`
#
# The CLI command mutates state immediately and invisibly. You type it, state
# changes, and the only record that it happened is your shell history. It
# imports one resource per invocation, cannot be reviewed before it runs, and
# on a mistake the fix is `state rm` and another undocumented command.
#
# An import block is configuration. It is committed, so the adoption is in the
# diff a reviewer reads; it is planned before it is applied, so `terraform
# plan` shows what will be adopted *and* whether adopting it would change
# anything; and it is declarative, so re-running is a no-op rather than an
# error. For infrastructure already serving traffic, "see the plan before
# state moves" is the entire safety property.
#
# ## The danger these blocks carry
#
# Import does not modify infrastructure. The *apply that follows* does. Once a
# resource is in state, Terraform will make reality match this configuration —
# and if the configuration is missing an attribute the real resource has, the
# plan proposes changing it. For most attributes that is an update in place.
# For some it is **destroy and recreate**:
#
#   - RDS: `identifier`, `engine`, most `db_subnet_group_name` changes
#   - Lambda: `function_name`, `runtime` vs `package_type`
#   - Security groups: `name`, `vpc_id`, `description`
#   - DynamoDB: `name`, the hash/range key schema
#
# `terraform plan` marks these `# forces replacement`. On the RDS instance
# that line means the database is deleted and a new empty one created. Every
# plan in this ticket gets read for that string before anything is applied.
#
# ## Deliberately not imported
#
#   - the S3 state bucket, because a config cannot safely manage the store
#     holding its own state: `terraform destroy` would delete the bucket
#     mid-run and orphan everything after it
#   - the default VPC, its subnets, and its route table, because destroy
#     would take out the network every other resource sits in

# --- Tier 1: cheap to get wrong -------------------------------------------

import {
  to = aws_ecr_repository.app
  id = "quotejar"
}

import {
  to = aws_dynamodb_table.rate_limits
  id = "quotejar-rate-limits"
}

import {
  to = aws_sns_topic.billing_alerts
  id = "arn:aws:sns:us-east-1:782747473074:quotejar-billing-alerts"
}

import {
  to = aws_cloudwatch_metric_alarm.estimated_charges_5usd
  id = "quotejar-estimated-charges-5usd"
}

import {
  to = aws_cloudwatch_metric_alarm.estimated_charges_10usd
  id = "quotejar-estimated-charges-10usd"
}

# Budgets are imported as AccountID:BudgetName, not by name alone -- budgets
# are an account-level service with no ARN of the usual shape.
import {
  to = aws_budgets_budget.monthly
  id = "782747473074:quotejar-monthly-10usd"
}

# --- Tier 2: IAM ----------------------------------------------------------

import {
  to = aws_iam_role.lambda
  id = "quotejar-lambda-role"
}

import {
  to = aws_iam_role.github_actions
  id = "quotejar-github-actions"
}

import {
  to = aws_iam_openid_connect_provider.github
  id = "arn:aws:iam::782747473074:oidc-provider/token.actions.githubusercontent.com"
}

# A role's permissions are separate resources from the role itself, and
# importing the role alone leaves them unmanaged -- the role would look
# adopted while every policy granting it anything stayed invisible to
# Terraform. Worse, an apply against a role with no policy blocks defined
# leaves the live policies in place but untracked, so the config claims a
# permission set it does not actually describe.
#
# Attachments (AWS-managed policies) import as "role-name/policy-arn".
import {
  to = aws_iam_role_policy_attachment.lambda_basic_execution
  id = "quotejar-lambda-role/arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

import {
  to = aws_iam_role_policy_attachment.lambda_vpc_access
  id = "quotejar-lambda-role/arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
}

# Inline policies import as "role-name:policy-name".
import {
  to = aws_iam_role_policy.lambda_read_own_secrets
  id = "quotejar-lambda-role:quotejar-read-own-secrets"
}

import {
  to = aws_iam_role_policy.lambda_rate_limit_table
  id = "quotejar-lambda-role:quotejar-rate-limit-table"
}

import {
  to = aws_iam_role_policy.github_actions_cd
  id = "quotejar-github-actions:quotejar-cd-permissions"
}

# --- Tier 3: networking ---------------------------------------------------

import {
  to = aws_security_group.rds
  id = "sg-0956a5f7b9950e1b2"
}

import {
  to = aws_security_group.lambda
  id = "sg-0c47444c43f3ed25f"
}

import {
  to = aws_security_group.vpc_endpoint
  id = "sg-04efb90f045da68c7"
}

import {
  to = aws_vpc_endpoint.secretsmanager
  id = "vpce-063ee61683bd56442"
}

import {
  to = aws_vpc_endpoint.dynamodb
  id = "vpce-08940f1ea5dae1a5c"
}

# --- Tier 4: the two that hurt --------------------------------------------
#
# Secrets Manager entries are imported as *containers*. The secret version
# holding the value is not managed here and must never be — see README.

# Imported by full ARN, not by name. Secrets Manager appends a random
# six-character suffix to every secret's ARN, and the import silently produces
# nothing when given the friendly name -- no error, the resource simply does
# not appear in the generated config, which is easy to miss in a batch this
# size. The suffix exists so that a deleted secret's name can be reused
# without a new secret inheriting grants made to the old one.
import {
  to = aws_secretsmanager_secret.database_url
  id = "arn:aws:secretsmanager:us-east-1:782747473074:secret:quotejar/database-url-NbsfeP"
}

import {
  to = aws_secretsmanager_secret.jwt_secret
  id = "arn:aws:secretsmanager:us-east-1:782747473074:secret:quotejar/jwt-secret-h7xgkg"
}

import {
  to = aws_db_instance.main
  id = "quotejar-db"
}

import {
  to = aws_lambda_function.api
  id = "quotejar-api"
}

import {
  to = aws_lambda_function_url.api
  id = "quotejar-api"
}
