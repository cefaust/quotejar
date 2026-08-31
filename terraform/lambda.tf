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
  architectures = ["x86_64"]

  # code_sha256 is deliberately absent.
  #
  # It is the digest of the deployed image -- a *description of the artefact*,
  # not a setting anyone declares. `-generate-config-out` emitted it as a
  # literal because it was reading a live resource, and a literal here pins the
  # config to whichever image happened to be deployed the day the config was
  # generated.
  #
  # Omitting it lets the provider treat it as computed: Terraform records
  # whatever is deployed and never proposes changing it.
  code_signing_config_arn = null
  description             = "QuoteJar API (FastAPI via Mangum) - QJ-3 - coldstart probe db 1786333836"
  filename                = null
  function_name           = "quotejar-api"
  handler                 = null
  # :latest, not a pinned SHA -- and this value is only ever read when the
  # function is *created*, since ignore_changes covers it thereafter.
  #
  # That creation case is the whole reason to care. A pinned SHA here means a
  # rebuild from scratch resurrects whichever image was current the day this
  # config was generated, quietly deploying old code during a recovery. :latest
  # gets whatever CD pushed most recently.
  #
  # cd.yml deliberately *deploys* by SHA and never by :latest, because a
  # mutable tag makes "what is running" unanswerable. That reasoning applies to
  # routine deploys; here the alternative is a tag that is guaranteed stale.
  image_uri    = "${aws_ecr_repository.app.repository_url}:latest"
  kms_key_arn  = null
  layers       = []
  memory_size  = var.lambda_memory_mb
  package_type = "Image"
  # false, not null. AWS stores no value at all here, so an unset attribute
  # plans as a change on every single run -- a permanent one-line diff that
  # teaches you to skim plan output, which is the habit that lets a
  # "forces replacement" line on the RDS instance slip past.
  publish                              = false
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
    security_group_ids          = [aws_security_group.lambda.id]
    subnet_ids                  = [var.private_subnet_id]
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
    # code_sha256 is listed as well as omitted above, deliberately.
    #
    # Omitting it from config is what stops the diff today. This entry is the
    # guard against someone re-adding it -- most plausibly by regenerating the
    # config with `-generate-config-out`, which emits it as a literal every
    # time. Without it, the first deploy after such a regeneration puts the
    # rollback back.
    ignore_changes = [image_uri, code_sha256, description]
  }
}

resource "aws_lambda_function_url" "api" {
  authorization_type = "NONE"
  function_name      = "quotejar-api"
  invoke_mode        = "BUFFERED"
  qualifier          = null
}
