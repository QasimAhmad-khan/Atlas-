"""Generate local-only secrets once; never print their values."""

import secrets
from pathlib import Path


def main() -> None:
    path = Path(".env")
    if path.exists():
        raise SystemExit(
            ".env already exists; retain its secrets and create the metrics-token file manually"
        )
    values = {
        name: secrets.token_urlsafe(32) for name in ("API_KEY", "METRICS_KEY", "GRAFANA_PASSWORD")
    }
    path.write_text("".join(f"{k}={v}\n" for k, v in values.items()), encoding="utf-8")
    directory = Path(".local-secrets")
    directory.mkdir(exist_ok=True)
    (directory / "metrics-token").write_text(values["METRICS_KEY"], encoding="utf-8")
    print("Created .env and the Prometheus bearer token. Keep both local.")


if __name__ == "__main__":
    main()
