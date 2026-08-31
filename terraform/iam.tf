# Roles, policies, and the GitHub OIDC provider.
#
# Two identities with different jobs:
#
#   - `lambda`: what the running function is allowed to do. Basic execution
#     for logs, VPC access for the ENIs, plus exactly two grants of its own --
#     read those two secrets, and read/write that one DynamoDB table.
#
#   - `github_actions`: what the deploy pipeline is allowed to do. Assumed via
#     OIDC, so no long-lived AWS key exists in GitHub to leak.
#
# The trust policy's `sub` condition matches on **numeric IDs**, not the
# documented `repo:owner/name:ref:...` form. AWS receives
# `repo:cefaust@101376746/quotejar@1322374978:ref:refs/heads/main`, and a
# policy written the documented way fails with an unhelpful "Not authorized to
# perform sts:AssumeRoleWithWebIdentity". That cost an afternoon in QJ-4; the
# IDs are immutable, which is the point -- renaming the repo does not silently
# hand access to whoever claims the old name.

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
      Resource = aws_ecr_repository.app.arn
      Sid      = "PushOnlyToTheQuotejarRepository"
      }, {
      Action   = ["lambda:UpdateFunctionCode", "lambda:GetFunction", "lambda:GetFunctionConfiguration", "lambda:PublishVersion", "lambda:GetFunctionUrlConfig"]
      Effect   = "Allow"
      Resource = aws_lambda_function.api.arn
      Sid      = "UpdateOnlyTheQuotejarFunction"
    }]
    Version = "2012-10-17"
  })
  role = aws_iam_role.github_actions.name
}

resource "aws_iam_openid_connect_provider" "github" {
  client_id_list  = ["sts.amazonaws.com"]
  tags            = {}
  tags_all        = {}
  thumbprint_list = ["ab9d0263244dd0326eb67015705a667e79cfe998"]
  url             = "https://token.actions.githubusercontent.com"
}

resource "aws_iam_role_policy_attachment" "lambda_vpc_access" {
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
  role       = "quotejar-lambda-role"
}

resource "aws_iam_role_policy" "lambda_rate_limit_table" {
  name = "quotejar-rate-limit-table"
  policy = jsonencode({
    Statement = [{
      Action   = ["dynamodb:UpdateItem", "dynamodb:GetItem"]
      Effect   = "Allow"
      Resource = aws_dynamodb_table.rate_limits.arn
      Sid      = "RateLimitCountersOnly"
    }]
    Version = "2012-10-17"
  })
  role = aws_iam_role.lambda.name
}

resource "aws_iam_role_policy" "lambda_read_own_secrets" {
  name = "quotejar-read-own-secrets"
  policy = jsonencode({
    Statement = [{
      Action   = ["secretsmanager:GetSecretValue"]
      Effect   = "Allow"
      Resource = [aws_secretsmanager_secret.database_url.arn, aws_secretsmanager_secret.jwt_secret.arn]
    }]
    Version = "2012-10-17"
  })
  role = aws_iam_role.lambda.name
}

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

resource "aws_iam_role_policy_attachment" "lambda_basic_execution" {
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
  role       = "quotejar-lambda-role"
}

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
        Federated = aws_iam_openid_connect_provider.github.arn
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
