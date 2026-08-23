# Billing guardrails.
#
# A budget and two alarms on EstimatedCharges, notifying an SNS topic. This is
# the cheapest infrastructure in the account and the reason an idle mistake
# gets noticed in hours rather than at the end of the month.
#
# EstimatedCharges is published only to us-east-1 regardless of where spend
# happens, which is one of the reasons everything here is single-region.
#
# Note these alarms read *gross usage*, before credits. They have never fired
# despite ~$10 of usage, because credits cover it -- so the alarm state and
# the amount actually billed are answering different questions.

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
          "AWS:SourceOwner" = data.aws_caller_identity.current.account_id
        }
      }
      Effect = "Allow"
      Principal = {
        AWS = "*"
      }
      Resource = "arn:aws:sns:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:quotejar-billing-alerts"
      Sid      = "__default_statement_ID"
    }]
    Version = "2008-10-17"
  })
  sqs_failure_feedback_role_arn    = null
  sqs_success_feedback_role_arn    = null
  sqs_success_feedback_sample_rate = 0
  tags                             = {}
  tags_all                         = {}
}

resource "aws_cloudwatch_metric_alarm" "estimated_charges_5usd" {
  actions_enabled     = true
  alarm_actions       = [aws_sns_topic.billing_alerts.arn]
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
  statistic                 = "Maximum"
  tags                      = {}
  tags_all                  = {}
  threshold                 = 5
  threshold_metric_id       = null
  treat_missing_data        = "notBreaching"
  unit                      = null
}

resource "aws_cloudwatch_metric_alarm" "estimated_charges_10usd" {
  actions_enabled     = true
  alarm_actions       = [aws_sns_topic.billing_alerts.arn]
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
  statistic                 = "Maximum"
  tags                      = {}
  tags_all                  = {}
  threshold                 = 10
  threshold_metric_id       = null
  treat_missing_data        = "notBreaching"
  unit                      = null
}

resource "aws_budgets_budget" "monthly" {
  account_id        = data.aws_caller_identity.current.account_id
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
