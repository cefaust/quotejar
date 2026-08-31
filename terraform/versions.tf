terraform {
  # Pinned to a minor range rather than left open. A state file written by a
  # newer Terraform cannot be read by an older one, so an unpinned version is
  # a way for one machine to lock everyone else out of the state.
  required_version = "~> 1.15"

  required_providers {
    aws = {
      source = "hashicorp/aws"
      # Pessimistic on the minor version: provider majors change resource
      # schemas, and a schema change on an imported resource shows up as a
      # diff against infrastructure nobody touched.
      version = "~> 6.0"
    }
  }

  # --- Remote state -------------------------------------------------------
  #
  # Why not local state. The state file is the only record mapping Terraform
  # addresses to real AWS resource IDs. On a laptop that means:
  #
  #   - it is invisible to everyone else, so a second person running apply
  #     starts from an empty state, sees no resources, and proposes creating
  #     a duplicate of production
  #   - it is one disk failure away from gone, and losing it does not delete
  #     the infrastructure, it orphans it -- every resource still running,
  #     none of it managed, and the only way back is to import all of it again
  #   - it cannot be locked, so nothing prevents two concurrent applies
  #   - it holds secrets in plaintext (see README) sitting in a working
  #     directory that is one `git add -A` away from being published
  #
  # S3 fixes the first three. Versioning on the bucket makes a corrupted or
  # truncated write recoverable rather than fatal.
  # The two literals below are the only hardcoded account/region values left in
  # this configuration, and they cannot be anything else: **a backend block
  # accepts no variables, locals, or interpolation of any kind.** Terraform
  # has to locate its state before it can evaluate a variable, so the values
  # that tell it where state lives cannot themselves come from state-dependent
  # evaluation. Everything else derives its account and region from data
  # sources.
  #
  # The alternative is `-backend-config=` on init, which moves the values to a
  # file or a flag rather than removing them. Not worth it for a single
  # environment.
  backend "s3" {
    bucket = "quotejar-tfstate-782747473074"
    key    = "quotejar/terraform.tfstate"
    region = "us-east-1"

    # Native S3 locking, via conditional writes on a .tflock object next to
    # the state. This replaces the old dynamodb_table lock, which needed a
    # whole extra table to hold one boolean and is deprecated as of provider
    # v6. Requires Terraform >= 1.10.
    #
    # What the lock actually prevents: two applies mutating state at the same
    # time. Both read the same state, both act on it, and the second write
    # clobbers the first -- so the state records only the second run's
    # changes while the first run's resources are live and now untracked.
    # Concretely: two `apply`s racing on this config, one creating the RDS
    # instance and one creating the Lambda, end with a state that knows about
    # exactly one of them. The orphan keeps billing and the next plan offers
    # to create a second copy.
    use_lockfile = true

    encrypt = true
  }
}
