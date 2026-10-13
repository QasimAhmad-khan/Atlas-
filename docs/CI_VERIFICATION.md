# Actual GitHub CI verification

Verified 14 October 2026, Asia/Karachi, for [PR #1](https://github.com/QasimAhmad-khan/Atlas-/pull/1), source commit `c41e29a10f2630d686fe8edbbd400319bdb80c7a`.

[Run 38477935037](https://github.com/QasimAhmad-khan/Atlas-/actions/runs/38477935037) completed successfully. This is an executed GitHub Actions run, not a workflow lint result.

| Job | Executed checks | Result |
| --- | --- | --- |
| quality | Locked dependencies, Ruff, formatting, mypy, PostgreSQL 16 expand migration/drift, pytest, dependency advisory audit | Passed; 73 tests, zero errors/failures/skips, 11.275 seconds |
| infrastructure | Terraform formatting/init/validate, mocked AWS security plan, Docker promtool rule validation and synthetic firing/recovery test | Passed; no AWS credentials or resources used |
| image | Actual Alpine image build, one-off migration, runtime/PostgreSQL smoke checks, Trivy 0.70.0 HIGH/CRITICAL and secret scan | Passed; zero findings at the configured scan severity |

The smoke script is mounted read-only into the built image. It executes the image's uvloop and application dependencies, uses a real PostgreSQL connection, checks live/readiness, denies unauthenticated reads/metrics, permits authenticated requests and creates/reads a durable job. It does not crawl external sites and is not copied into the deployed image.

## Failures corrected

1. The initial Terraform lock included the Windows package content hash but lacked Linux's. `terraform providers lock -platform=windows_amd64 -platform=linux_amd64` fetched signed provider packages and added the Linux hash. Read-only lock enforcement remains enabled.
2. The old Trivy action depended on removed `setup-trivy@v0.2.1`. Both workflows now use the verified commit for v0.36.0, including pinned transitive action references. The HIGH/CRITICAL failure gate remains enabled.
3. Once scanning could run, the Debian base reported 44 HIGH OS package findings, including repeated findings across packages from the same vulnerable source. No patched versions were reported for them. Python dependencies and secret scanning had no findings. The Python 3.12 Alpine 3.23 image passed the same gate; the scan identifies its actual OS as Alpine 3.23.6. The added smoke check verifies the libc/runtime change against PostgreSQL.

## Raw evidence

* [GitHub run/job metadata](../artifacts/ci/github-run.json)
* [Actual Linux JUnit](../artifacts/ci/tests.xml)
* [Dependency audit](../artifacts/ci/dependencies.json)
* [Debian image scan before remediation](../artifacts/ci/image-scan-before.json)
* [Alpine image scan](../artifacts/ci/image-scan.json)

Downloaded artifact ZIPs matched GitHub's reported SHA256 digests, recorded in the run metadata. Test and scan files were read directly from those artifacts, without reconstructing results. The native Windows benchmark/dashboard evidence remains separate.

## Limits

CI has not deployed AWS infrastructure, published an ECR release, demonstrated cloud rollback/restoration, run the full Compose/Tempo stack or delivered real operational alerts. Scanning is a point-in-time result at HIGH/CRITICAL severity, not proof that all vulnerabilities or application bugs are absent. The PR remains subject to owner review and has not been merged by this session.
