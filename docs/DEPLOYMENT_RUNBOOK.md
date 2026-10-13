# Deployment runbook

## Local

Use Python 3.12+, uv 0.13.0 and Docker Compose. Run `uv sync --frozen --extra dev`, `uv run python scripts/configure_local.py`, then `docker compose up --build --wait app worker prometheus collector tempo grafana`. Job submission requires `Authorization: Bearer <API_KEY from .env>`. Health probes remain unauthenticated. The database uses demo credentials and a localhost-only published port. Do not reuse these credentials or expose this stack publicly.

## AWS prerequisites and approval

Prepare an approved account, issued ACM certificate and hostname, existing application/telemetry secrets, telemetry backend, notification email addresses, and a protected GitHub `demo` deployment environment. If a GitHub OIDC provider already exists, supply its ARN. Set trusted repository/environment names. Use an encrypted, locked Terraform backend for shared state. Validate with `terraform fmt -check`, `terraform init`, `terraform validate`, `terraform test`, and a reviewed real-account `terraform plan`. Permission reachability and prices still need account verification. Obtain explicit approval for that plan and recurring spend before apply.

Terraform initially creates services at zero replicas if no image digest is provided. This prepares the infrastructure without running an unknown application image; it still incurs infrastructure charges. Publish a scanned immutable image, execute the one-off migration/bootstrap task, then start API and worker services through the release process. Never run application-container startup migrations. Bootstrap uses admin credentials and creates the DML-only IAM application role; its privileges exclude modification of `alembic_version`.

Export `terraform output -json deployment > deployment.json` to the protected release configuration. Set the deployment environment's OIDC release role and region, API HTTPS base URL, submission key, and deployment JSON. Add DNS to the ALB under the issued certificate hostname. A request made directly to the generated ALB DNS name will not match your certificate; use the hostname you configured.

The release process must migrate, verify task exit code, deploy both services, verify that the requested revision actually became primary (a waiter alone can succeed after automatic rollback), run authenticated smoke tests, and write an outcome artifact. A failed release restores both previous task definitions and replica counts, then verifies those revisions are primary and healthy. Application rollback never reverses a schema change. See `ROLLBACK_RUNBOOK.md` for a controlled bad-release experiment.

## Verification

Validate 401/403/429 and request limits, readiness during a DB fault, fresh worker heartbeats, successful jobs, trace continuity, alert firing/recovery, circuit breaker behavior and absence of public RDS/metrics access. Record AWS CLI/API output and real dashboard screenshots with revision and time. No AWS deployment, remote CI or full Docker stack has been run in the current environment.
