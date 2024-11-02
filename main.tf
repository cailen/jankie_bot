# # module.lambda_function.lambda_function_qualified_arn

module "lambda_function" {
  #checkov:skip=CKV_TF_1: "Choosing not to use commit hash"
  source  = "terraform-aws-modules/lambda/aws"
  version = "~> 7.0"

  function_name = "jankie-bot-${random_pet.this.id}"
  description   = "Jankie Bot"
  handler       = "app.lambda_handler"
  runtime       = "python3.11"

  publish        = true
  lambda_at_edge = false

  allowed_triggers = {
    RunEveryFiveMins = {
      principal  = "events.amazonaws.com"
      source_arn = aws_cloudwatch_event_rule.run_every_5_minutes.arn
    }
  }

  environment_variables = {
    DRY_RUN   = false
    SUBREDDIT = "jankie_test"
  }

  timeout = 30

  attach_policy_json = true
  policy_json        = data.aws_iam_policy_document.lambda_paramstore_policy.json

  source_path = "app"
}

##################
# Extra resources
##################

resource "random_pet" "this" {
  length = 2
}

data "aws_iam_policy_document" "lambda_paramstore_policy" {
  statement {
    actions = [
      "ssm:DescribeParameter*",
      "ssm:GetParameter*",
      "ssm:PutParameter*",
    ]

    resources = [
      aws_ssm_parameter.creds.arn,
      aws_ssm_parameter.last_comment_id.arn,
    ]
  }
}

##################################
# Cloudwatch Events (EventBridge)
##################################
resource "aws_cloudwatch_event_rule" "run_every_5_minutes" {
  name                = "run-every-5-minutes"
  schedule_expression = "rate(5 minutes)"

  tags = {
    Name = "run-every-5-minutes"
  }
}

resource "aws_cloudwatch_event_target" "run_every_5_minutes" {
  rule = aws_cloudwatch_event_rule.run_every_5_minutes.name
  arn  = module.lambda_function.lambda_function_arn
}

resource "aws_ssm_parameter" "last_comment_id" {
  #checkov:skip=CKV_AWS_337: "NO CMK"
  name  = "/jankie/reddit/last_comment_id"
  type  = "SecureString"
  value = "0"

  lifecycle {
    ignore_changes = [value]
  }
}

resource "aws_ssm_parameter" "creds" {
  #checkov:skip=CKV_AWS_337: "NO CMK"
  name = "/jankie/reddit/creds"
  type = "SecureString"
  value = jsonencode({
    client_id     = ""
    client_secret = ""
    user_agent    = "JankieBot by u/JankieBot"
    username      = ""
    password      = ""
  })

  lifecycle {
    ignore_changes = [value]
  }
}
