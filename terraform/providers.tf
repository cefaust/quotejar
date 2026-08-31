provider "aws" {
  region = var.aws_region

  # No default_tags here, deliberately, and it is worth saying why since it is
  # the first thing a reviewer will look for.
  #
  # default_tags applies tags to every resource the provider manages. None of
  # the resources being adopted in this ticket carry those tags today, so
  # switching it on would make `terraform plan` propose a tag change on all of
  # them -- and the acceptance gate for this work is a plan that proposes
  # *nothing*. A plan full of tag diffs is a plan nobody reads carefully, which
  # is exactly how a `forces replacement` line on the RDS instance gets
  # scrolled past.
  #
  # Tagging is worth doing as its own change, once the import is proven clean
  # and the diff is small enough to actually read.
}

# Account ID and region are read from the caller rather than written down.
# Hardcoding either means the config only works from one account, and an
# account ID pasted into a repository is a small but free piece of recon for
# anyone reading it.
data "aws_caller_identity" "current" {}

data "aws_region" "current" {}
