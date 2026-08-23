# Secrets Manager entries.
#
# ## The rule this file exists to keep
#
# Terraform manages the secret *container* -- its name, description, and
# deletion behaviour. It does not manage the secret *value*. There is no
# `aws_secretsmanager_secret_version` resource here, and there must not be
# one, because the value would then have to come from somewhere Terraform can
# read: a variable, a file, or a literal. All three end up in the state file.
#
# The values were set once, by hand:
#
#     aws secretsmanager put-secret-value \
#       --secret-id quotejar/database-url --secret-string '<value>'
#
# and are read at Lambda cold start by app/config.py. Rotating one is a CLI
# call, not a Terraform change.
#
# ## Where secret values still leak, even doing this
#
# Keeping values out of .tf files is necessary and not sufficient. State is
# the leak. `terraform show -json` on this configuration prints, in plaintext:
#
#   - the RDS master password, because `aws_db_instance.password` is stored in
#     state whether or not it appears in configuration
#   - the full DATABASE_URL, if any resource ever reads that secret's value
#
# Terraform state has no concept of an encrypted field. `sensitive = true`
# only redacts CLI *output*; the value sits in the JSON in the clear. That is
# why the state bucket has default encryption, blocks public access, and is
# versioned -- and why `*.tfstate` is in .gitignore. A state file committed to
# git publishes the database password to everyone who can read the repository,
# and rewriting history does not un-publish it.
#
# The secondary leaks worth naming:
#
#   - `terraform plan` output shows values it is about to change, so a plan
#     pasted into a PR comment or a CI log can expose them. This is one of the
#     reasons the CI workflow runs no plan.
#   - a saved plan file (`-out`) embeds the same values, which is why
#     `*.tfplan` is also gitignored.
#   - CloudTrail records the API calls, not the values, so it is not a leak --
#     but `secretsmanager:GetSecretValue` being auditable is what makes a
#     leaked value detectable after the fact.

resource "aws_secretsmanager_secret" "database_url" {
  name        = "quotejar/database-url"
  description = "QuoteJar production DATABASE_URL (includes RDS master credentials)"

  # Both attributes below are provider-side only: AWS does not store either,
  # and they take effect only when Terraform *deletes* the secret. They are
  # set explicitly rather than left null because an unset value plans as a
  # change on every run -- a permanent one-line diff that trains you to skim
  # plan output, which is the habit this ticket is trying to avoid.
  #
  # 30 days is the AWS default recovery window. Deleting a secret schedules it
  # rather than removing it, and the name stays reserved for the whole window,
  # so a teardown-and-rebuild inside 30 days cannot reuse these names without
  # `--force-delete-without-recovery`. Noted in the teardown runbook.
  recovery_window_in_days        = 30
  force_overwrite_replica_secret = false
}

resource "aws_secretsmanager_secret" "jwt_secret" {
  name        = "quotejar/jwt-secret"
  description = "QuoteJar production JWT signing secret"

  recovery_window_in_days        = 30
  force_overwrite_replica_secret = false
}
