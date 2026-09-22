from __future__ import annotations

from atlaspipe.parsing.links import classify_links


def test_classify_links_filters_non_web_links_and_deduplicates() -> None:
    links = classify_links(
        "https://example.com/a",
        ["/b", "/b", "mailto:test@example.com", "https://elsewhere.test/x"],
    )

    assert [link.url for link in links] == [
        "https://example.com/b",
        "https://elsewhere.test/x",
    ]
    assert [link.is_internal for link in links] == [True, False]
