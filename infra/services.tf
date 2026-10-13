locals {
  image    = var.image_digest == "" ? "${aws_ecr_repository.app.repository_url}:bootstrap" : "${aws_ecr_repository.app.repository_url}@${var.image_digest}"
  services = { api = var.api_count, worker = var.worker_count }
  base_environment = [
    { name = "ENVIRONMENT", value = "production" },
    { name = "DB_HOST", value = aws_db_instance.main.address },
    { name = "DB_NAME", value = "atlaspipe" },
    { name = "DATABASE_SSL", value = "true" },
    { name = "DATABASE_CA_FILE", value = "/app/certs/global-bundle.pem" },
    { name = "AWS_REGION", value = var.region },
    { name = "RELEASE", value = var.image_digest == "" ? "bootstrap" : var.image_digest },
    { name = "OTEL_EXPORTER_OTLP_ENDPOINT", value = "http://localhost:4318" }
  ]
}
resource "aws_ecs_cluster" "main" {
  name = var.name
  setting {
    name  = "containerInsights"
    value = "enabled"
  }
}
resource "aws_ecs_task_definition" "app" {
  for_each                 = toset(["api", "worker", "migration"])
  family                   = "${var.name}-${each.key}"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = each.key == "migration" ? "256" : "512"
  memory                   = each.key == "migration" ? "512" : "1024"
  execution_role_arn       = aws_iam_role.execution[each.key].arn
  task_role_arn            = aws_iam_role.task[each.key].arn
  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }
  container_definitions = jsonencode(concat([{
    name         = "app", image = local.image, essential = true, stopTimeout = 40,
    command      = each.key == "api" ? ["uvicorn", "atlaspipe.api.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"] : each.key == "worker" ? ["atlaspipe-worker"] : ["sh", "-c", "alembic upgrade head && python -m atlaspipe.bootstrap"],
    portMappings = each.key == "api" ? [{ containerPort = 8000, protocol = "tcp" }] : [],
    environment = concat(local.base_environment, [
      { name = "SERVICE", value = each.key },
      { name = "DATABASE_AUTH", value = each.key == "migration" ? "password" : "iam" },
      { name = "DB_USERNAME", value = each.key == "migration" ? "atlasadmin" : "atlaspipe_app" },
      { name = "WORKER_METRICS_PORT", value = each.key == "worker" ? "8081" : "0" }
    ]),
    secrets = each.key == "migration" ? [{ name = "DB_PASSWORD", valueFrom = "${aws_db_instance.main.master_user_secret[0].secret_arn}:password::" }] : concat(
      [{ name = "METRICS_KEY", valueFrom = "${var.app_secret_arn}:METRICS_KEY::" }],
      each.key == "api" ? [{ name = "API_KEY", valueFrom = "${var.app_secret_arn}:API_KEY::" }] : []
    ),
    logConfiguration = { logDriver = "awslogs", options = { awslogs-group = aws_cloudwatch_log_group.app[each.key].name, awslogs-region = var.region, awslogs-stream-prefix = "app" } },
    healthCheck      = each.key == "migration" ? null : { command = each.key == "worker" ? ["CMD", "python", "-m", "atlaspipe.worker_health"] : ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/ready',timeout=3)"], interval = 10, timeout = 5, retries = 3, startPeriod = 30 }
    }], each.key == "migration" ? [] : [{
    name   = "collector", image = "otel/opentelemetry-collector-contrib:0.140.0", essential = false,
    memory = 128, command = ["--config=env:OTEL_CONFIG"],
    environment = [
      { name = "OTEL_CONFIG", value = templatefile("${path.module}/collector.yml.tftpl", { service = each.key, port = each.key == "api" ? 8000 : 8081 }) },
      { name = "REMOTE_OTLP_ENDPOINT", value = var.telemetry_otlp_endpoint }
    ],
    secrets          = [{ name = "METRICS_KEY", valueFrom = "${var.app_secret_arn}:METRICS_KEY::" }, { name = "REMOTE_OTLP_AUTHORIZATION", valueFrom = var.telemetry_secret_arn }],
    logConfiguration = { logDriver = "awslogs", options = { awslogs-group = aws_cloudwatch_log_group.app[each.key].name, awslogs-region = var.region, awslogs-stream-prefix = "collector" } }
  }]))
}
resource "aws_lb" "api" {
  name                       = var.name
  load_balancer_type         = "application"
  internal                   = false
  security_groups            = [aws_security_group.alb.id]
  subnets                    = aws_subnet.public[*].id
  drop_invalid_header_fields = true
  enable_deletion_protection = var.deletion_protection
}
resource "aws_lb_target_group" "api" {
  name                 = var.name
  port                 = 8000
  protocol             = "HTTP"
  target_type          = "ip"
  vpc_id               = aws_vpc.main.id
  deregistration_delay = 30
  health_check {
    path                = "/ready"
    matcher             = "200"
    interval            = 15
    timeout             = 5
    healthy_threshold   = 2
    unhealthy_threshold = 2
  }
}
resource "aws_lb_listener" "https" {
  load_balancer_arn = aws_lb.api.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = var.certificate_arn
  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }
}
resource "aws_lb_listener_rule" "internal" {
  listener_arn = aws_lb_listener.https.arn
  priority     = 1
  condition {
    path_pattern { values = ["/internal", "/internal/*"] }
  }
  action {
    type = "fixed-response"
    fixed_response {
      content_type = "text/plain"
      message_body = "Not found"
      status_code  = "404"
    }
  }
}
resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.api.arn
  port              = 80
  protocol          = "HTTP"
  default_action {
    type = "redirect"
    redirect {
      port        = "443"
      protocol    = "HTTPS"
      status_code = "HTTP_301"
    }
  }
}
resource "aws_cloudwatch_metric_alarm" "api_errors" {
  alarm_name          = "${var.name}-api-errors"
  namespace           = "AWS/ApplicationELB"
  metric_name         = "HTTPCode_Target_5XX_Count"
  dimensions          = { LoadBalancer = aws_lb.api.arn_suffix, TargetGroup = aws_lb_target_group.api.arn_suffix }
  statistic           = "Sum"
  period              = 60
  evaluation_periods  = 2
  threshold           = 5
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alarms.arn]
  ok_actions          = [aws_sns_topic.alarms.arn]
}
resource "aws_cloudwatch_metric_alarm" "worker_cpu" {
  alarm_name          = "${var.name}-worker-cpu"
  namespace           = "AWS/ECS"
  metric_name         = "CPUUtilization"
  dimensions          = { ClusterName = aws_ecs_cluster.main.name, ServiceName = "${var.name}-worker" }
  statistic           = "Average"
  period              = 60
  evaluation_periods  = 3
  threshold           = 95
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alarms.arn]
  ok_actions          = [aws_sns_topic.alarms.arn]
}
resource "aws_ecs_service" "app" {
  for_each                           = local.services
  name                               = "${var.name}-${each.key}"
  cluster                            = aws_ecs_cluster.main.id
  task_definition                    = aws_ecs_task_definition.app[each.key].arn
  desired_count                      = var.image_digest == "" ? 0 : each.value
  launch_type                        = "FARGATE"
  platform_version                   = "1.4.0"
  deployment_minimum_healthy_percent = 100
  deployment_maximum_percent         = 200
  health_check_grace_period_seconds  = each.key == "api" ? 60 : null
  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.tasks.id]
    assign_public_ip = false
  }
  dynamic "load_balancer" {
    for_each = each.key == "api" ? [1] : []
    content {
      target_group_arn = aws_lb_target_group.api.arn
      container_name   = "app"
      container_port   = 8000
    }
  }
  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }
  alarms {
    alarm_names = [each.key == "api" ? aws_cloudwatch_metric_alarm.api_errors.alarm_name : aws_cloudwatch_metric_alarm.worker_cpu.alarm_name]
    enable      = true
    rollback    = true
  }
  lifecycle { ignore_changes = [task_definition, desired_count] }
  depends_on = [aws_lb_listener.https, aws_lb_listener_rule.internal, aws_iam_role_policy.execution]
}
