resource "aws_wafv2_web_acl" "api" {
  name  = "${var.name}-api"
  scope = "REGIONAL"
  default_action {
    allow {}
  }
  rule {
    name     = "shared-ingress-rate-limit"
    priority = 1
    action {
      block {
        custom_response {
          response_code = 429
          response_header {
            name  = "Retry-After"
            value = "60"
          }
        }
      }
    }
    statement {
      rate_based_statement {
        limit                 = 300
        aggregate_key_type    = "IP"
        evaluation_window_sec = 60
      }
    }
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${var.name}-rate-limit"
      sampled_requests_enabled   = false
    }
  }
  visibility_config {
    cloudwatch_metrics_enabled = true
    metric_name                = "${var.name}-waf"
    sampled_requests_enabled   = false
  }
}
resource "aws_wafv2_web_acl_association" "api" {
  resource_arn = aws_lb.api.arn
  web_acl_arn  = aws_wafv2_web_acl.api.arn
}
