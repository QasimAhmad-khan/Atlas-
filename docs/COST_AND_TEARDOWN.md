# Cost and teardown

No AWS resources have been created and no current dollar estimate has been measured. Before approval, obtain a regional AWS Pricing Calculator estimate for RDS (storage/backups), Fargate app/collector tasks, ALB, NAT gateway hours and data processing, IPv4 addresses, ECR, CloudWatch/container insights, managed telemetry and egress. The default single NAT may cost more than the small API workload. Budget alerts do not impose a spending cap and billing data can lag.

Use a dedicated demo account/environment with an owner and a planned removal time. Create a reviewed real-account plan; verify ACM, secret/KMS ARNs, GitHub OIDC environment restrictions, remote state encryption/locking, alarms and notification subscription confirmation. Never add plaintext secrets to tfvars. Local Terraform state is ignored but must be secured; configure an encrypted S3 backend with restricted access and native S3 locking before a shared deployment.

After approval, record `terraform output -json`, deployed image digest, resource IDs and actual billing data. Configure AWS Budgets notifications and verify email confirmation for SNS alarms. A 50 USD monthly alert threshold is a notification default, not a quoted cost or spending authorization.

Teardown is destructive and requires owner approval. Stop release activity, save test evidence, choose a unique final RDS snapshot identifier, verify a backup/restore procedure, then set `deletion_protection=false` and apply only that reviewed change. Save and review a `terraform plan -destroy`; then apply the approved destroy plan. ECR must be emptied explicitly before repository destruction (force-delete is intentionally disabled). Review snapshots, untagged/retained images, Secrets Manager secrets supplied outside Terraform, DNS, certificates, telemetry retention, log groups and storage for residual charges. Do not delete final snapshots or external secrets automatically.

The teardown definition and protections are tested with a mocked Terraform provider. Actual AWS teardown and isolated RDS snapshot restore are unverified and cannot be claimed as demonstrated recovery.
