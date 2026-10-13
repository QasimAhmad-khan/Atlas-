resource "aws_db_subnet_group" "main" {
  name       = var.name
  subnet_ids = aws_subnet.database[*].id
}
resource "aws_db_parameter_group" "main" {
  name   = var.name
  family = "postgres16"
  parameter {
    name  = "rds.force_ssl"
    value = "1"
  }
}
resource "aws_db_instance" "main" {
  identifier                          = var.name
  engine                              = "postgres"
  engine_version                      = "16"
  instance_class                      = "db.t4g.micro"
  allocated_storage                   = 20
  max_allocated_storage               = 40
  storage_encrypted                   = true
  db_name                             = "atlaspipe"
  username                            = "atlasadmin"
  manage_master_user_password         = true
  iam_database_authentication_enabled = true
  db_subnet_group_name                = aws_db_subnet_group.main.name
  parameter_group_name                = aws_db_parameter_group.main.name
  vpc_security_group_ids              = [aws_security_group.database.id]
  publicly_accessible                 = false
  multi_az                            = var.multi_az
  backup_retention_period             = 7
  deletion_protection                 = var.deletion_protection
  skip_final_snapshot                 = false
  final_snapshot_identifier           = "${var.name}-final"
  enabled_cloudwatch_logs_exports     = ["postgresql"]
  auto_minor_version_upgrade          = true
}
resource "aws_ecr_repository" "app" {
  name                 = var.name
  image_tag_mutability = "IMMUTABLE"
  image_scanning_configuration { scan_on_push = true }
  encryption_configuration { encryption_type = "AES256" }
}
resource "aws_ecr_lifecycle_policy" "app" {
  repository = aws_ecr_repository.app.name
  policy = jsonencode({ rules = [{ rulePriority = 1, description = "Remove untagged build images", selection = {
    tagStatus = "untagged", countType = "sinceImagePushed", countUnit = "days", countNumber = 7
  }, action = { type = "expire" } }] })
}
resource "aws_cloudwatch_log_group" "app" {
  for_each          = toset(["api", "worker", "migration"])
  name              = "/ecs/${var.name}/${each.key}"
  retention_in_days = 7
}
resource "aws_sns_topic" "alarms" { name = "${var.name}-alarms" }
resource "aws_sns_topic_subscription" "email" {
  topic_arn = aws_sns_topic.alarms.arn
  protocol  = "email"
  endpoint  = var.alarm_email
}
resource "aws_budgets_budget" "demo" {
  name         = var.name
  budget_type  = "COST"
  limit_amount = tostring(var.monthly_budget_usd)
  limit_unit   = "USD"
  time_unit    = "MONTHLY"
  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 80
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = [var.budget_email]
  }
}
