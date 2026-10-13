output "deployment" {
  value = {
    region           = var.region
    cluster          = aws_ecs_cluster.main.name
    repository_url   = aws_ecr_repository.app.repository_url
    release_role_arn = aws_iam_role.release.arn
    alb_dns          = aws_lb.api.dns_name
    services         = { for name, service in aws_ecs_service.app : name => service.name }
    task_definitions = { for name, task in aws_ecs_task_definition.app : name => task.arn }
    desired_counts   = local.services
    network          = { awsvpcConfiguration = { subnets = aws_subnet.private[*].id, securityGroups = [aws_security_group.tasks.id], assignPublicIp = "DISABLED" } }
  }
}
output "database_endpoint" { value = aws_db_instance.main.address }
