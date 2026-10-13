locals {
  ecs_trust = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Principal = { Service = "ecs-tasks.amazonaws.com" }, Action = "sts:AssumeRole" }] })
  oidc_arn  = var.github_oidc_provider_arn != "" ? var.github_oidc_provider_arn : aws_iam_openid_connect_provider.github[0].arn
}
resource "aws_iam_role" "execution" {
  for_each           = toset(["api", "worker", "migration"])
  name               = "${var.name}-${each.key}-execution"
  assume_role_policy = local.ecs_trust
}
resource "aws_iam_role_policy" "execution" {
  for_each = aws_iam_role.execution
  role     = each.value.id
  policy = jsonencode({ Version = "2012-10-17", Statement = concat([
    { Effect = "Allow", Action = ["ecr:GetAuthorizationToken"], Resource = "*" },
    { Effect = "Allow", Action = ["ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer", "ecr:BatchCheckLayerAvailability"], Resource = aws_ecr_repository.app.arn },
    { Effect = "Allow", Action = ["logs:CreateLogStream", "logs:PutLogEvents"], Resource = "${aws_cloudwatch_log_group.app[each.key].arn}:*" },
    { Effect = "Allow", Action = ["secretsmanager:GetSecretValue"], Resource = each.key == "migration" ? [aws_db_instance.main.master_user_secret[0].secret_arn] : [var.app_secret_arn, var.telemetry_secret_arn] }
    ], length(var.secret_kms_key_arns) > 0 ? [{ Effect = "Allow", Action = ["kms:Decrypt"], Resource = var.secret_kms_key_arns, Condition = { StringEquals = { "kms:ViaService" = "secretsmanager.${var.region}.amazonaws.com" } } }] : [])
  })
}
resource "aws_iam_role" "task" {
  for_each           = toset(["api", "worker", "migration"])
  name               = "${var.name}-${each.key}-task"
  assume_role_policy = local.ecs_trust
}
resource "aws_iam_role_policy" "database" {
  for_each = toset(["api", "worker"])
  role     = aws_iam_role.task[each.key].id
  policy = jsonencode({ Version = "2012-10-17", Statement = [{
    Effect   = "Allow", Action = ["rds-db:connect"],
    Resource = "arn:aws:rds-db:${var.region}:${data.aws_caller_identity.current.account_id}:dbuser:${aws_db_instance.main.resource_id}/atlaspipe_app"
  }] })
}
resource "aws_iam_openid_connect_provider" "github" {
  count          = var.github_oidc_provider_arn == "" ? 1 : 0
  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]
}
resource "aws_iam_role" "release" {
  name = "${var.name}-release"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{
    Effect = "Allow", Principal = { Federated = local.oidc_arn }, Action = "sts:AssumeRoleWithWebIdentity",
    Condition = { StringEquals = {
      "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com",
      "token.actions.githubusercontent.com:sub" = "repo:${var.github_repository}:environment:${var.github_environment}"
    } }
  }] })
}
resource "aws_iam_role_policy" "release" {
  role = aws_iam_role.release.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [
    { Effect = "Allow", Action = ["ecr:GetAuthorizationToken"], Resource = "*" },
    { Effect = "Allow", Action = ["ecr:BatchCheckLayerAvailability", "ecr:InitiateLayerUpload", "ecr:UploadLayerPart", "ecr:CompleteLayerUpload", "ecr:PutImage", "ecr:DescribeImages"], Resource = aws_ecr_repository.app.arn },
    { Effect = "Allow", Action = ["ecs:RegisterTaskDefinition", "ecs:DescribeTaskDefinition", "ecs:DescribeTasks", "ecs:ListTasks"], Resource = "*" },
    { Effect = "Allow", Action = ["ecs:UpdateService", "ecs:DescribeServices"], Resource = values(aws_ecs_service.app)[*].id },
    { Effect = "Allow", Action = ["ecs:RunTask"], Resource = "arn:aws:ecs:${var.region}:${data.aws_caller_identity.current.account_id}:task-definition/${var.name}-migration:*", Condition = { ArnEquals = { "ecs:cluster" = aws_ecs_cluster.main.arn } } },
    { Effect = "Allow", Action = ["ecs:StopTask"], Resource = "arn:aws:ecs:${var.region}:${data.aws_caller_identity.current.account_id}:task/${aws_ecs_cluster.main.name}/*" },
    { Effect = "Allow", Action = ["iam:PassRole"], Resource = concat(values(aws_iam_role.task)[*].arn, values(aws_iam_role.execution)[*].arn), Condition = { StringEquals = { "iam:PassedToService" = "ecs-tasks.amazonaws.com" } } }
  ] })
}
