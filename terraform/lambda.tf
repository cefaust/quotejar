# The function and its public URL.
#
# Terraform owns the function's *shape* -- memory, timeout, role, networking,
# concurrency. CD owns what runs inside it. See the lifecycle block for why
# that split has to be explicit.
#
# The Function URL has auth type NONE, which is deliberate rather than an
# oversight: authorisation is the application's JWT layer. AWS_IAM here would
# mean every caller needed SigV4-signed requests, which no browser client can
# produce.

resource "aws_lambda_function" "api" {
  architectures                        = ["x86_64"]
  code_sha256                          = "11d977d19832a31de223bc255ac4e000d605dd0c0a3b17924996b4ae4db62d66"
  code_signing_config_arn              = null
  description                          = "QuoteJar API (FastAPI via Mangum) - QJ-3 - coldstart probe db 1786333836"
  filename                             = null
  function_name                        = "quotejar-api"
  handler                              = null
  image_uri                            = "${aws_ecr_repository.app.repository_url}:66ef1a1e021c912957442cd0717135f0ce21322e"
  kms_key_arn                          = null
  layers                               = []
  memory_size                          = var.lambda_memory_mb
  package_type                         = "Image"
  publish                              = null
  publish_to                           = null
  replace_security_groups_on_destroy   = null
  replacement_security_group_ids       = null
  reserved_concurrent_executions       = var.lambda_reserved_concurrency
  role                                 = aws_iam_role.lambda.arn
  runtime                              = null
  s3_bucket                            = null
  s3_key                               = null
  s3_object_version                    = null
  skip_destroy                         = false
  source_kms_key_arn                   = null
  tags                                 = {}
  tags_all                             = {}
  timeout                              = var.lambda_timeout_seconds
  use_resource_timeout_for_propagation = null
  environment {
    variables = {
      DATABASE_URL_SECRET_ID = aws_secretsmanager_secret.database_url.name
      JWT_SECRET_SECRET_ID   = aws_secretsmanager_secret.jwt_secret.name
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

  # CD, not Terraform, owns which image is deployed.
  #
  # .github/workflows/cd.yml runs `aws lambda update-function-code` with the
  # commit SHA on every push to main. Without this block the two fight: CD
  # deploys abcdef, Terraform still has the SHA that was current when this
  # config was generated, and the next `terraform apply` quietly rolls
  # production back to an older image. The rollback would look like a
  # successful apply.
  #
  # ignore_changes makes that explicit -- Terraform provisions the function and
  # stops caring what runs inside it. description moves with the deploy for the
  # same reason (the CD probe rewrites it).
  #
  # The alternative is moving deploys into Terraform, which is out of scope
  # here and has its own cost: every application deploy would then need an
  # apply with write credentials, which is exactly what the CI decision in
  # this ticket avoided.
  lifecycle {
    ignore_changes = [image_uri, description]
  }
}

resource "aws_lambda_function_url" "api" {
  authorization_type = "NONE"
  function_name      = "quotejar-api"
  invoke_mode        = "BUFFERED"
  qualifier          = null
}
