# The database.
#
# The resource most likely to be destroyed by a careless plan, so read any
# diff here before applying. `identifier`, `engine`, and subnet group changes
# force replacement, and replacement of a database means an empty one.
#
# **skip_final_snapshot is true, and that is dangerous under Terraform.**
#
# It was set that way in QJ-3 for a good reason: a retained snapshot keeps
# billing for storage after the instance is gone, which is exactly the
# forgotten charge the teardown runbook exists to prevent. When teardown was a
# deliberate CLI command typed once, that trade was fine.
#
# It is a worse trade now. `terraform destroy` needs no confirmation beyond
# -auto-approve, and a mistargeted destroy -- or a `forces replacement` line
# scrolled past in a plan -- deletes this database with **no snapshot and no
# recovery**. The setting has not been changed, because flipping it would put
# a real cost back on every teardown; the guard below is the answer instead.
#
# prevent_destroy makes Terraform refuse to destroy this resource at all. It
# is a configuration-only meta-argument -- nothing in AWS changes and it
# creates no diff -- and removing it is a deliberate edit somebody has to
# make, which is precisely the pause that matters here.
#
# The master password is not in this configuration and cannot be -- it is in
# state regardless, which is the leak documented in secrets.tf.

resource "aws_db_instance" "main" {
  allocated_storage                     = var.db_allocated_storage_gb
  allow_major_version_upgrade           = null
  apply_immediately                     = null
  auto_minor_version_upgrade            = true
  availability_zone                     = "us-east-1b"
  backup_retention_period               = 1
  backup_target                         = "region"
  backup_window                         = "08:16-08:46"
  ca_cert_identifier                    = "rds-ca-rsa2048-g1"
  copy_tags_to_snapshot                 = false
  custom_iam_instance_profile           = null
  customer_owned_ip_enabled             = false
  database_insights_mode                = "standard"
  db_name                               = "quotejar"
  db_subnet_group_name                  = "default"
  dedicated_log_volume                  = false
  delete_automated_backups              = true
  deletion_protection                   = false
  domain                                = null
  domain_auth_secret_arn                = null
  domain_iam_role_name                  = null
  domain_ou                             = null
  enabled_cloudwatch_logs_exports       = []
  engine                                = "postgres"
  engine_lifecycle_support              = "open-source-rds-extended-support"
  engine_version                        = "16.14"
  final_snapshot_identifier             = null
  iam_database_authentication_enabled   = false
  identifier                            = "quotejar-db"
  instance_class                        = var.db_instance_class
  iops                                  = 3000
  license_model                         = "postgresql-license"
  maintenance_window                    = "tue:03:30-tue:04:00"
  manage_master_user_password           = null
  max_allocated_storage                 = 0
  monitoring_interval                   = 0
  multi_az                              = false
  network_type                          = "IPV4"
  option_group_name                     = "default:postgres-16"
  parameter_group_name                  = "default.postgres16"
  password                              = null # sensitive
  password_wo                           = null # sensitive
  password_wo_version                   = null
  performance_insights_enabled          = false
  performance_insights_retention_period = 0
  port                                  = 5432
  publicly_accessible                   = true
  replicate_source_db                   = null
  skip_final_snapshot                   = true
  storage_encrypted                     = false
  storage_throughput                    = 125
  storage_type                          = "gp3"
  tags                                  = {}
  tags_all                              = {}
  upgrade_storage_config                = null
  username                              = "quotejar"
  vpc_security_group_ids                = [aws_security_group.rds.id]

  lifecycle {
    # Refuses `terraform destroy` on this resource. See the note above:
    # skip_final_snapshot is true, so a destroy here leaves no snapshot and
    # no way back. Removing this guard has to be a deliberate edit.
    prevent_destroy = true
  }
}
