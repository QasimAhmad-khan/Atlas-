from atlaspipe.observability.logging import redact_secrets


def test_logs_redact_credentials_and_url_queries_recursively() -> None:
    result = redact_secrets(
        None,
        "info",
        {
            "authorization": "Bearer private",
            "api_read_key": "private",
            "metrics_key": "private",
            "nested": {"password": "private"},
            "event": "fetch https://u:private@example.com/path?key=private",
        },
    )
    assert "private" not in str(result)
    assert result["event"] == "fetch https://example.com/path"


def test_redaction_handles_malformed_urls_without_crashing_logging() -> None:
    result = redact_secrets(None, "error", {"event": "invalid http://[malformed"})
    assert "[invalid-url]" in result["event"]
