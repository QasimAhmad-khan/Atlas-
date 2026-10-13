mock_provider "aws" {
  mock_data "aws_availability_zones" {
    defaults = { names = ["us-east-1a", "us-east-1b"] }
  }
  mock_data "aws_caller_identity" {
    defaults = { account_id = "123456789012" }
  }
}
override_resource {
  target = aws_db_instance.main
  values = {
    address     = "demo.example.rds.amazonaws.com"
    resource_id = "db-TEST"
    master_user_secret = [{
      secret_arn    = "arn:aws:secretsmanager:us-east-1:123456789012:secret:rds-admin-123456"
      secret_status = "active"
      kms_key_id    = "arn:aws:kms:us-east-1:123456789012:key/00000000-0000-0000-0000-000000000000"
    }]
  }
}
variables {
  certificate_arn         = "arn:aws:acm:us-east-1:123456789012:certificate/00000000-0000-0000-0000-000000000000"
  app_secret_arn          = "arn:aws:secretsmanager:us-east-1:123456789012:secret:app-123456"
  telemetry_secret_arn    = "arn:aws:secretsmanager:us-east-1:123456789012:secret:telemetry-123456"
  telemetry_otlp_endpoint = "https://telemetry.example.invalid"
  budget_email            = "owner@example.invalid"
  alarm_email             = "owner@example.invalid"
  image_digest            = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
  api_count               = 2
  worker_count            = 3
}
run "private_database_and_independent_services" {
  command = plan
  assert {
    condition     = !aws_db_instance.main.publicly_accessible && aws_db_instance.main.storage_encrypted && aws_db_instance.main.manage_master_user_password && aws_db_instance.main.iam_database_authentication_enabled
    error_message = "RDS must be private, encrypted, managed-secret and IAM authenticated."
  }
  assert {
    condition     = aws_ecs_service.app["api"].desired_count == 2 && aws_ecs_service.app["worker"].desired_count == 3
    error_message = "API and worker replicas must scale independently."
  }
  assert {
    condition     = alltrue([for service in values(aws_ecs_service.app) : !one(service.network_configuration).assign_public_ip && one(service.deployment_circuit_breaker).rollback && one(service.alarms).rollback])
    error_message = "Services require private IPs, circuit breakers and alarm rollback."
  }
  assert {
    condition     = one(one(aws_lb_listener_rule.internal.action).fixed_response).status_code == "404"
    error_message = "Public traffic must not reach internal metrics."
  }
  assert {
    condition     = aws_db_instance.main.deletion_protection && !aws_db_instance.main.skip_final_snapshot
    error_message = "Destruction must require an explicit protection change and a final snapshot."
  }
  assert {
    condition     = one(one(one(aws_wafv2_web_acl.api.rule).statement).rate_based_statement).evaluation_window_sec == 60
    error_message = "Ingress limiting must use shared WAF state across API replicas."
  }
}
