# __generated__ by Terraform
# Please review these resources and move them into your main configuration files.

# __generated__ by Terraform from "quotejar-github-actions:quotejar-cd-permissions"
resource "aws_iam_role_policy" "github_actions_cd" {
  name = "quotejar-cd-permissions"
  policy = jsonencode({
    Statement = [{
      Action   = "ecr:GetAuthorizationToken"
      Effect   = "Allow"
      Resource = "*"
      Sid      = "EcrAuthTokenIsAccountWide"
      }, {
      Action   = ["ecr:BatchCheckLayerAvailability", "ecr:InitiateLayerUpload", "ecr:UploadLayerPart", "ecr:CompleteLayerUpload", "ecr:PutImage", "ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer", "ecr:DescribeImages"]
      Effect   = "Allow"
      Resource = "arn:aws:ecr:us-east-1:782747473074:repository/quotejar"
      Sid      = "PushOnlyToTheQuotejarRepository"
      }, {
      Action   = ["lambda:UpdateFunctionCode", "lambda:GetFunction", "lambda:GetFunctionConfiguration", "lambda:PublishVersion", "lambda:GetFunctionUrlConfig"]
      Effect   = "Allow"
      Resource = "arn:aws:lambda:us-east-1:782747473074:function:quotejar-api"
      Sid      = "UpdateOnlyTheQuotejarFunction"
    }]
    Version = "2012-10-17"
  })
  role = "quotejar-github-actions"
}

# __generated__ by Terraform
resource "aws_iam_openid_connect_provider" "github" {
  client_id_list  = ["sts.amazonaws.com"]
  tags            = {}
  tags_all        = {}
  thumbprint_list = ["ab9d0263244dd0326eb67015705a667e79cfe998"]
  url             = "https://token.actions.githubusercontent.com"
}

# __generated__ by Terraform from "quotejar-lambda-role/arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
resource "aws_iam_role_policy_attachment" "lambda_vpc_access" {
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
  role       = "quotejar-lambda-role"
}

# __generated__ by Terraform from "quotejar-lambda-role:quotejar-rate-limit-table"
resource "aws_iam_role_policy" "lambda_rate_limit_table" {
  name = "quotejar-rate-limit-table"
  policy = jsonencode({
    Statement = [{
      Action   = ["dynamodb:UpdateItem", "dynamodb:GetItem"]
      Effect   = "Allow"
      Resource = "arn:aws:dynamodb:us-east-1:782747473074:table/quotejar-rate-limits"
      Sid      = "RateLimitCountersOnly"
    }]
    Version = "2012-10-17"
  })
  role = "quotejar-lambda-role"
}

# __generated__ by Terraform
resource "aws_sns_topic" "billing_alerts" {
  application_failure_feedback_role_arn    = null
  application_success_feedback_role_arn    = null
  application_success_feedback_sample_rate = 0
  archive_policy                           = null
  content_based_deduplication              = false
  delivery_policy                          = null
  display_name                             = null
  fifo_topic                               = false
  firehose_failure_feedback_role_arn       = null
  firehose_success_feedback_role_arn       = null
  firehose_success_feedback_sample_rate    = 0
  http_failure_feedback_role_arn           = null
  http_success_feedback_role_arn           = null
  http_success_feedback_sample_rate        = 0
  kms_master_key_id                        = null
  lambda_failure_feedback_role_arn         = null
  lambda_success_feedback_role_arn         = null
  lambda_success_feedback_sample_rate      = 0
  name                                     = "quotejar-billing-alerts"
  policy = jsonencode({
    Id = "__default_policy_ID"
    Statement = [{
      Action = ["SNS:GetTopicAttributes", "SNS:SetTopicAttributes", "SNS:AddPermission", "SNS:RemovePermission", "SNS:DeleteTopic", "SNS:Subscribe", "SNS:ListSubscriptionsByTopic", "SNS:Publish"]
      Condition = {
        StringEquals = {
          "AWS:SourceOwner" = "782747473074"
        }
      }
      Effect = "Allow"
      Principal = {
        AWS = "*"
      }
      Resource = "arn:aws:sns:us-east-1:782747473074:quotejar-billing-alerts"
      Sid      = "__default_statement_ID"
    }]
    Version = "2008-10-17"
  })
  region                           = "us-east-1"
  sqs_failure_feedback_role_arn    = null
  sqs_success_feedback_role_arn    = null
  sqs_success_feedback_sample_rate = 0
  tags                             = {}
  tags_all                         = {}
}

# __generated__ by Terraform
resource "aws_db_instance" "main" {
  allocated_storage                     = 20
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
  instance_class                        = "db.t4g.micro"
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
  region                                = "us-east-1"
  replicate_source_db                   = null
  skip_final_snapshot                   = true
  storage_encrypted                     = false
  storage_throughput                    = 125
  storage_type                          = "gp3"
  tags                                  = {}
  tags_all                              = {}
  upgrade_storage_config                = null
  username                              = "quotejar"
  vpc_security_group_ids                = ["sg-0956a5f7b9950e1b2"]
}

# __generated__ by Terraform from "quotejar"
resource "aws_ecr_repository" "app" {
  force_delete         = null
  image_tag_mutability = "MUTABLE"
  name                 = "quotejar"
  region               = "us-east-1"
  tags                 = {}
  tags_all             = {}
  encryption_configuration {
    encryption_type = "AES256"
  }
  image_scanning_configuration {
    scan_on_push = true
  }
}

# __generated__ by Terraform from "quotejar-api"
resource "aws_lambda_function" "api" {
  architectures                        = ["x86_64"]
  code_sha256                          = "11d977d19832a31de223bc255ac4e000d605dd0c0a3b17924996b4ae4db62d66"
  code_signing_config_arn              = null
  description                          = "QuoteJar API (FastAPI via Mangum) - QJ-3 - coldstart probe db 1786333836"
  filename                             = null
  function_name                        = "quotejar-api"
  handler                              = null
  image_uri                            = "782747473074.dkr.ecr.us-east-1.amazonaws.com/quotejar:66ef1a1e021c912957442cd0717135f0ce21322e"
  kms_key_arn                          = null
  layers                               = []
  memory_size                          = 1024
  package_type                         = "Image"
  publish                              = null
  publish_to                           = null
  region                               = "us-east-1"
  replace_security_groups_on_destroy   = null
  replacement_security_group_ids       = null
  reserved_concurrent_executions       = 5
  role                                 = "arn:aws:iam::782747473074:role/quotejar-lambda-role"
  runtime                              = null
  s3_bucket                            = null
  s3_key                               = null
  s3_object_version                    = null
  skip_destroy                         = false
  source_kms_key_arn                   = null
  tags                                 = {}
  tags_all                             = {}
  timeout                              = 30
  use_resource_timeout_for_propagation = null
  environment {
    variables = {
      DATABASE_URL_SECRET_ID = "quotejar/database-url"
      JWT_SECRET_SECRET_ID   = "quotejar/jwt-secret"
    }
  }
  ephemeral_storage {
    size = 512
  }
  logging_config {
    application_log_level = null
    log_format            = "Text"
    log_group             = "/aws/lambda/quotejar-api"
    system_log_level      = null
  }
  tracing_config {
    mode = "PassThrough"
  }
  vpc_config {
    ipv6_allowed_for_dual_stack = false
    security_group_ids          = ["sg-0c47444c43f3ed25f"]
    subnet_ids                  = ["subnet-05ea50db0fd8c9ab0"]
  }
}

# __generated__ by Terraform from "sg-04efb90f045da68c7"
resource "aws_security_group" "vpc_endpoint" {
  description = "QuoteJar: HTTPS from Lambda to Secrets Manager VPC endpoint"
  egress = [{
    cidr_blocks      = ["0.0.0.0/0"]
    description      = ""
    from_port        = 0
    ipv6_cidr_blocks = []
    prefix_list_ids  = []
    protocol         = "-1"
    security_groups  = []
    self             = false
    to_port          = 0
  }]
  ingress = [{
    cidr_blocks      = []
    description      = "quotejar lambda"
    from_port        = 443
    ipv6_cidr_blocks = []
    prefix_list_ids  = []
    protocol         = "tcp"
    security_groups  = ["sg-0c47444c43f3ed25f"]
    self             = false
    to_port          = 443
  }]
  name                   = "quotejar-vpce-sg"
  region                 = "us-east-1"
  revoke_rules_on_delete = null
  tags                   = {}
  tags_all               = {}
  vpc_id                 = "vpc-0a7d500454d8fec5b"
}

# __generated__ by Terraform from "quotejar-lambda-role:quotejar-read-own-secrets"
resource "aws_iam_role_policy" "lambda_read_own_secrets" {
  name = "quotejar-read-own-secrets"
  policy = jsonencode({
    Statement = [{
      Action   = ["secretsmanager:GetSecretValue"]
      Effect   = "Allow"
      Resource = ["arn:aws:secretsmanager:us-east-1:782747473074:secret:quotejar/database-url-NbsfeP", "arn:aws:secretsmanager:us-east-1:782747473074:secret:quotejar/jwt-secret-h7xgkg"]
    }]
    Version = "2012-10-17"
  })
  role = "quotejar-lambda-role"
}

# __generated__ by Terraform from "sg-0956a5f7b9950e1b2"
resource "aws_security_group" "rds" {
  description = "QuoteJar RDS: postgres from admin IP and App Runner only"
  egress = [{
    cidr_blocks      = ["0.0.0.0/0"]
    description      = ""
    from_port        = 0
    ipv6_cidr_blocks = []
    prefix_list_ids  = []
    protocol         = "-1"
    security_groups  = []
    self             = false
    to_port          = 0
  }]
  ingress = [{
    cidr_blocks      = []
    description      = "quotejar lambda"
    from_port        = 5432
    ipv6_cidr_blocks = []
    prefix_list_ids  = []
    protocol         = "tcp"
    security_groups  = ["sg-0c47444c43f3ed25f"]
    self             = false
    to_port          = 5432
  }]
  name                   = "quotejar-rds-sg"
  region                 = "us-east-1"
  revoke_rules_on_delete = null
  tags                   = {}
  tags_all               = {}
  vpc_id                 = "vpc-0a7d500454d8fec5b"
}

# __generated__ by Terraform from "sg-0c47444c43f3ed25f"
resource "aws_security_group" "lambda" {
  description = "QuoteJar Lambda: egress to RDS and Secrets Manager endpoint"
  egress = [{
    cidr_blocks      = ["0.0.0.0/0"]
    description      = ""
    from_port        = 0
    ipv6_cidr_blocks = []
    prefix_list_ids  = []
    protocol         = "-1"
    security_groups  = []
    self             = false
    to_port          = 0
  }]
  ingress                = []
  name                   = "quotejar-lambda-sg"
  region                 = "us-east-1"
  revoke_rules_on_delete = null
  tags                   = {}
  tags_all               = {}
  vpc_id                 = "vpc-0a7d500454d8fec5b"
}

# __generated__ by Terraform from "quotejar-lambda-role"
resource "aws_iam_role" "lambda" {
  assume_role_policy = jsonencode({
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "lambda.amazonaws.com"
      }
    }]
    Version = "2012-10-17"
  })
  description           = "Execution role for the QuoteJar Lambda function"
  force_detach_policies = false
  max_session_duration  = 3600
  name                  = "quotejar-lambda-role"
  path                  = "/"
  permissions_boundary  = null
  tags                  = {}
  tags_all              = {}
}

# __generated__ by Terraform from "quotejar-lambda-role/arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
resource "aws_iam_role_policy_attachment" "lambda_basic_execution" {
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
  role       = "quotejar-lambda-role"
}

# __generated__ by Terraform from "quotejar-api"
resource "aws_lambda_function_url" "api" {
  authorization_type = "NONE"
  function_name      = "quotejar-api"
  invoke_mode        = "BUFFERED"
  qualifier          = null
  region             = "us-east-1"
}

# __generated__ by Terraform from "quotejar-github-actions"
resource "aws_iam_role" "github_actions" {
  assume_role_policy = jsonencode({
    Statement = [{
      Action = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
          "token.actions.githubusercontent.com:sub" = "repo:cefaust@101376746/quotejar@1322374978:ref:refs/heads/main"
        }
      }
      Effect = "Allow"
      Principal = {
        Federated = "arn:aws:iam::782747473074:oidc-provider/token.actions.githubusercontent.com"
      }
    }]
    Version = "2012-10-17"
  })
  description           = "Assumed by GitHub Actions via OIDC for CD. Scoped to main only."
  force_detach_policies = false
  max_session_duration  = 3600
  name                  = "quotejar-github-actions"
  path                  = "/"
  permissions_boundary  = null
  tags                  = {}
  tags_all              = {}
}

# __generated__ by Terraform
resource "aws_cloudwatch_metric_alarm" "estimated_charges_5usd" {
  actions_enabled     = true
  alarm_actions       = ["arn:aws:sns:us-east-1:782747473074:quotejar-billing-alerts"]
  alarm_description   = "QuoteJar: estimated AWS charges exceeded $5 (early warning)"
  alarm_name          = "quotejar-estimated-charges-5usd"
  comparison_operator = "GreaterThanThreshold"
  dimensions = {
    Currency = "USD"
  }
  evaluation_periods        = 1
  extended_statistic        = null
  insufficient_data_actions = []
  metric_name               = "EstimatedCharges"
  namespace                 = "AWS/Billing"
  ok_actions                = []
  period                    = 21600
  region                    = "us-east-1"
  statistic                 = "Maximum"
  tags                      = {}
  tags_all                  = {}
  threshold                 = 5
  threshold_metric_id       = null
  treat_missing_data        = "notBreaching"
  unit                      = null
}

# __generated__ by Terraform
resource "aws_cloudwatch_metric_alarm" "estimated_charges_10usd" {
  actions_enabled     = true
  alarm_actions       = ["arn:aws:sns:us-east-1:782747473074:quotejar-billing-alerts"]
  alarm_description   = "QuoteJar: estimated AWS charges exceeded $10"
  alarm_name          = "quotejar-estimated-charges-10usd"
  comparison_operator = "GreaterThanThreshold"
  dimensions = {
    Currency = "USD"
  }
  evaluation_periods        = 1
  extended_statistic        = null
  insufficient_data_actions = []
  metric_name               = "EstimatedCharges"
  namespace                 = "AWS/Billing"
  ok_actions                = []
  period                    = 21600
  region                    = "us-east-1"
  statistic                 = "Maximum"
  tags                      = {}
  tags_all                  = {}
  threshold                 = 10
  threshold_metric_id       = null
  treat_missing_data        = "notBreaching"
  unit                      = null
}

# __generated__ by Terraform
resource "aws_dynamodb_table" "rate_limits" {
  billing_mode                = "PAY_PER_REQUEST"
  deletion_protection_enabled = false
  hash_key                    = "pk"
  name                        = "quotejar-rate-limits"
  range_key                   = null
  read_capacity               = 0
  region                      = "us-east-1"
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

# __generated__ by Terraform
resource "aws_vpc_endpoint" "dynamodb" {
  auto_accept     = null
  ip_address_type = "ipv4"
  policy = jsonencode({
    Statement = [{
      Action    = "*"
      Effect    = "Allow"
      Principal = "*"
      Resource  = "*"
    }]
    Version = "2008-10-17"
  })
  private_dns_enabled        = false
  region                     = "us-east-1"
  resource_configuration_arn = null
  route_table_ids            = ["rtb-08a5b21d76235cd7f"]
  security_group_ids         = []
  service_name               = "com.amazonaws.us-east-1.dynamodb"
  service_network_arn        = null
  service_region             = "us-east-1"
  subnet_ids                 = []
  tags                       = {}
  tags_all                   = {}
  vpc_endpoint_type          = "Gateway"
  vpc_id                     = "vpc-0a7d500454d8fec5b"
  dns_options {
    dns_record_ip_type                             = "service-defined"
    private_dns_only_for_inbound_resolver_endpoint = false
  }
}

# __generated__ by Terraform
resource "aws_vpc_endpoint" "secretsmanager" {
  auto_accept     = null
  ip_address_type = "ipv4"
  policy = jsonencode({
    Statement = [{
      Action    = "*"
      Effect    = "Allow"
      Principal = "*"
      Resource  = "*"
    }]
  })
  private_dns_enabled        = true
  region                     = "us-east-1"
  resource_configuration_arn = null
  route_table_ids            = []
  security_group_ids         = ["sg-04efb90f045da68c7"]
  service_name               = "com.amazonaws.us-east-1.secretsmanager"
  service_network_arn        = null
  service_region             = "us-east-1"
  subnet_ids                 = ["subnet-05ea50db0fd8c9ab0"]
  tags                       = {}
  tags_all                   = {}
  vpc_endpoint_type          = "Interface"
  vpc_id                     = "vpc-0a7d500454d8fec5b"
  dns_options {
    dns_record_ip_type                             = "ipv4"
    private_dns_only_for_inbound_resolver_endpoint = false
  }
  subnet_configuration {
    ipv4      = "172.31.92.57"
    ipv6      = null
    subnet_id = "subnet-05ea50db0fd8c9ab0"
  }
}

# __generated__ by Terraform
resource "aws_budgets_budget" "monthly" {
  account_id        = "782747473074"
  billing_view_arn  = null
  budget_type       = "COST"
  limit_amount      = "10.0"
  limit_unit        = "USD"
  name              = "quotejar-monthly-10usd"
  tags              = {}
  tags_all          = {}
  time_period_end   = "2087-06-15_00:00"
  time_period_start = "2026-08-01_00:00"
  time_unit         = "MONTHLY"
  cost_types {
    include_credit             = false
    include_discount           = true
    include_other_subscription = true
    include_recurring          = true
    include_refund             = false
    include_subscription       = true
    include_support            = true
    include_tax                = true
    include_upfront            = true
    use_amortized              = false
    use_blended                = false
  }
  notification {
    comparison_operator        = "GREATER_THAN"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = ["cefaust82@gmail.com"]
    subscriber_sns_topic_arns  = []
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
  }
  notification {
    comparison_operator        = "GREATER_THAN"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = ["cefaust82@gmail.com"]
    subscriber_sns_topic_arns  = []
    threshold                  = 50
    threshold_type             = "PERCENTAGE"
  }
  notification {
    comparison_operator        = "GREATER_THAN"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = ["cefaust82@gmail.com"]
    subscriber_sns_topic_arns  = []
    threshold                  = 80
    threshold_type             = "PERCENTAGE"
  }
  notification {
    comparison_operator        = "GREATER_THAN"
    notification_type          = "FORECASTED"
    subscriber_email_addresses = ["cefaust82@gmail.com"]
    subscriber_sns_topic_arns  = []
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
  }
}
