from __future__ import annotations

from atlaspipe.parsing.html_parser import HtmlMetadataParser


def test_html_parser_extracts_metadata_and_links() -> None:
    html = """
    <html>
      <head>
        <title> Example page </title>
        <meta name="description" content=" Demo description ">
        <link rel="canonical" href="https://example.com/canonical">
      </head>
      <body>
        Contact ops@example.com
        <a href="/internal">Internal</a>
        <a href="https://other.example/path">External</a>
      </body>
    </html>
    """
    parsed = HtmlMetadataParser().parse(url="https://example.com/page", html=html)

    assert parsed.title == "Example page"
    assert parsed.description == "Demo description"
    assert parsed.canonical_url == "https://example.com/canonical"
    assert parsed.internal_link_count == 1
    assert parsed.external_link_count == 1
    assert parsed.email_domains == ["example.com"]


def test_html_parser_handles_malformed_html() -> None:
    parsed = HtmlMetadataParser().parse(url="https://example.com", html="<title>Broken")
    assert parsed.title == "Broken"
