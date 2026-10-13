variable "region" {
  type    = string
  default = "us-east-1"
}
variable "name" {
  type    = string
  default = "atlaspipe-demo"
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{2,21}$", var.name))
    error_message = "Use a short lowercase AWS resource prefix."
  }
}
variable "github_repository" {
  type    = string
  default = "QasimAhmad-khan/Atlas-"
}
variable "github_environment" {
  type    = string
  default = "demo"
}
variable "github_oidc_provider_arn" {
  type    = string
  default = ""
}
variable "certificate_arn" {
  type = string
  validation {
    condition     = can(regex("^arn:aws:acm:", var.certificate_arn))
    error_message = "Provide an issued ACM certificate in the ALB region."
  }
}
variable "app_secret_arn" {
  type        = string
  description = "Existing Secrets Manager JSON secret with API_KEY and METRICS_KEY (32+ characters each). Terraform never reads secret values."
  validation {
    condition     = can(regex("^arn:aws:secretsmanager:", var.app_secret_arn))
    error_message = "Provide an existing Secrets Manager ARN."
  }
}
variable "telemetry_secret_arn" {
  type        = string
  description = "Existing secret whose value is the complete remote OTLP Authorization header."
}
variable "telemetry_otlp_endpoint" {
  type = string
  validation {
    condition     = startswith(var.telemetry_otlp_endpoint, "https://")
    error_message = "Use an HTTPS OTLP backend base endpoint."
  }
}
variable "secret_kms_key_arns" {
  type    = list(string)
  default = []
}
variable "image_digest" {
  type    = string
  default = ""
  validation {
    condition     = var.image_digest == "" || can(regex("^sha256:[a-f0-9]{64}$", var.image_digest))
    error_message = "Use an immutable sha256 image digest."
  }
}
variable "api_count" {
  type    = number
  default = 1
  validation {
    condition     = var.api_count >= 1 && floor(var.api_count) == var.api_count
    error_message = "API count must be a positive integer."
  }
}
variable "worker_count" {
  type    = number
  default = 2
  validation {
    condition     = var.worker_count >= 1 && floor(var.worker_count) == var.worker_count
    error_message = "Worker count must be a positive integer."
  }
}
variable "multi_az" {
  type    = bool
  default = false
}
variable "nat_per_az" {
  type    = bool
  default = false
}
variable "budget_email" {
  type = string
}
variable "monthly_budget_usd" {
  type    = number
  default = 50
}
variable "alarm_email" {
  type = string
}
variable "deletion_protection" {
  type    = bool
  default = true
}
