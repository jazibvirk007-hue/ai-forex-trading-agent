from __future__ import annotations

import asyncio
import html
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Iterable

import httpx


_TAG_RE = re.compile(r"<[^>]+>")


@dataclass(frozen=True)
class ResearchItem:
    title: str
    summary: str
    link: str
    published_at: str | None
    source: str


@dataclass(frozen=True)
class ResearchSnapshot:
    symbol: str
    items: tuple[ResearchItem, ...]

    def prompt_text(self, max_chars: int = 7000) -> str:
        if not self.items:
            return "No external headlines were configured or matched."
        chunks = []
        used = 0
        for item in self.items:
            line = f"- [{item.source}] {item.title}: {item.summary}".strip()
            if used + len(line) > max_chars:
                break
            chunks.append(line)
            used += len(line)
        return "\n".join(chunks)


def _clean(value: str | None) -> str:
    text = html.unescape(value or "")
    return " ".join(_TAG_RE.sub(" ", text).split())


def _published(value: str | None) -> str | None:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat()
    except (TypeError, ValueError):
        return value[:80]


def _symbol_terms(symbol: str) -> tuple[str, ...]:
    upper = re.sub(r"[^A-Z0-9]", "", symbol.upper())
    terms = {upper}
    if len(upper) == 6 and upper.isalpha():
        terms.update({upper[:3], upper[3:]})
    aliases = {
        "EUR": "euro",
        "USD": "dollar",
        "GBP": "sterling",
        "JPY": "yen",
        "XAU": "gold",
        "XAG": "silver",
        "BTC": "bitcoin",
        "ETH": "ethereum",
    }
    for key, alias in aliases.items():
        if key in upper:
            terms.add(alias.upper())
    return tuple(sorted(terms))


class RSSResearchProvider:
    """Fetches user-configured RSS/Atom feeds without requiring a paid data vendor."""

    def __init__(self, feed_urls: Iterable[str], timeout: float = 12.0) -> None:
        self.feed_urls = tuple(url.strip() for url in feed_urls if url.strip())
        self.timeout = timeout

    async def _fetch_one(self, url: str) -> list[ResearchItem]:
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
            response = await client.get(
                url,
                headers={"User-Agent": "TJ-Trading-OS/0.3 research-feed"},
            )
        response.raise_for_status()
        root = ET.fromstring(response.text)
        host = httpx.URL(url).host or url
        items: list[ResearchItem] = []

        rss_items = root.findall(".//item")
        if rss_items:
            for node in rss_items[:40]:
                items.append(
                    ResearchItem(
                        title=_clean(node.findtext("title")),
                        summary=_clean(
                            node.findtext("description") or node.findtext("summary")
                        ),
                        link=_clean(node.findtext("link")),
                        published_at=_published(
                            node.findtext("pubDate") or node.findtext("published")
                        ),
                        source=host,
                    )
                )
            return items

        ns = {"atom": "http://www.w3.org/2005/Atom"}
        for node in root.findall(".//atom:entry", ns)[:40]:
            link_node = node.find("atom:link", ns)
            items.append(
                ResearchItem(
                    title=_clean(node.findtext("atom:title", default="", namespaces=ns)),
                    summary=_clean(
                        node.findtext("atom:summary", default="", namespaces=ns)
                        or node.findtext("atom:content", default="", namespaces=ns)
                    ),
                    link=(link_node.attrib.get("href", "") if link_node is not None else ""),
                    published_at=_published(
                        node.findtext("atom:published", default="", namespaces=ns)
                        or node.findtext("atom:updated", default="", namespaces=ns)
                    ),
                    source=host,
                )
            )
        return items

    async def fetch(self, symbol: str, max_items: int = 16) -> ResearchSnapshot:
        if not self.feed_urls:
            return ResearchSnapshot(symbol, ())
        results = await asyncio.gather(
            *(self._fetch_one(url) for url in self.feed_urls),
            return_exceptions=True,
        )
        all_items: list[ResearchItem] = []
        for result in results:
            if isinstance(result, list):
                all_items.extend(result)
        terms = _symbol_terms(symbol)
        matching = [
            item
            for item in all_items
            if any(
                term in f"{item.title} {item.summary}".upper()
                for term in terms
            )
        ]
        selected = matching if matching else all_items
        return ResearchSnapshot(symbol, tuple(selected[:max_items]))
