# Actual local dashboard evidence

Captured 14 October 2026, Asia/Karachi, from Grafana 12.2.1 and Prometheus 3.5.0 running as temporary native Windows processes. API and worker used the local PostgreSQL `atlaspipe_perf` database with 10,000 seeded pages. Scrapes used the application's separate bearer credential. No token or generated Grafana admin password is included.

* `grafana-api.jpg`: HTTP throughput, latency, errors and frontier state.
* `grafana-worker.jpg`: pending age, one healthy idle worker and heartbeat age.
* `grafana-db.jpg`: query latency and pool/error panels.
* `grafana-health.json`: actual Grafana health/version response.
* `prometheus-targets.json`: both real scrape targets up with no scrape error.
* `prometheus-rules.json`: actual loaded rules and their states at capture time.

The repository dashboard JSON was provisioned into this Grafana process. Only environment wiring differed from Compose: localhost Prometheus datasource, local dashboard path, local bearer-token file and static localhost scrape addresses. Grafana and Prometheus listened on loopback. Temporary Grafana anonymous access was Viewer only; Compose retains generated admin-password authentication.

A separate ten-second authenticated k6 burst supplied traffic for these graphs. Prometheus's five-minute rates smooth that burst, so they differ from per-run k6 throughput. The idle worker has no processed-outcome series; Windows also lacks the Linux process-memory metric. These are expected empty panels, not fabricated values. Actual API memory samples are in `artifacts/performance/api-resources.json`.

Screenshots were captured from the real browser UI, without retouching. The temporary services were stopped after capture. No Docker/Tempo/cloud integration or external alert notification was verified by these images.
