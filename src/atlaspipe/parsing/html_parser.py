from __future__ import annotations

from dataclasses import dataclass

from bs4 import BeautifulSoup

from atlaspipe.parsing.links import ClassifiedLink, classify_links
from atlaspipe.parsing.metadata import (
    detect_email_domains,
    detect_technology_hints,
    normalize_whitespace,
)


@dataclass(frozen=True)
class ParsedPage:
    title: str | None
    description: str | None
    canonical_url: str | None
    text: str
    links: list[ClassifiedLink]
    email_domains: list[str]
    technology_hints: list[str]

    @property
    def internal_link_count(self) -> int:
        return sum(1 for link in self.links if link.is_internal)

    @property
    def external_link_count(self) -> int:
        return sum(1 for link in self.links if not link.is_internal)

    @property
    def outbound_link_count(self) -> int:
        return len(self.links)


class HtmlMetadataParser:
    def parse(
        self,
        *,
        url: str,
        html: str,
        headers: dict[str, str] | None = None,
    ) -> ParsedPage:
        soup = BeautifulSoup(html, "html.parser")

        title = normalize_whitespace(soup.title.get_text(" ", strip=True)) if soup.title else None
        description = self._meta_content(soup, "description")
        canonical_tag = soup.find("link", rel=lambda value: value and "canonical" in value)
        canonical_url = (
            str(canonical_tag.get("href")).strip()
            if canonical_tag is not None and canonical_tag.get("href")
            else None
        )
        hrefs = [str(tag.get("href")) for tag in soup.find_all("a", href=True)]

        for noisy in soup(["script", "style", "noscript"]):
            noisy.decompose()
        text = normalize_whitespace(soup.get_text(" ", strip=True))

        return ParsedPage(
            title=title,
            description=description,
            canonical_url=canonical_url,
            text=text,
            links=classify_links(url, hrefs),
            email_domains=detect_email_domains(text),
            technology_hints=detect_technology_hints(html, headers),
        )

    @staticmethod
    def _meta_content(soup: BeautifulSoup, name: str) -> str | None:
        tag = soup.find("meta", attrs={"name": name})
        if tag is None:
            tag = soup.find("meta", attrs={"property": f"og:{name}"})
        content = tag.get("content") if tag is not None else None
        return normalize_whitespace(str(content)) if content else None
