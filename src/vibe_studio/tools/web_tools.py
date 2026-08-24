"""WebTools — High-speed HTTP-based web research, URL fetching, and search.

Allows the agent to search DuckDuckGo, fetch static/dynamic web pages,
extract readable markdown/text, and extract links without full browser overhead.
"""
from __future__ import annotations

import logging
import re
import urllib.parse
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _html_to_clean_text(html: str) -> str:
    """Strip script/style tags and clean HTML into readable markdown/text."""
    try:
        import markdownify  # type: ignore
        return markdownify.markdownify(html, heading_style="ATX", strip=["script", "style", "nav", "footer"]).strip()
    except Exception:
        # Fallback regex cleaner
        text = re.sub(r"<(script|style|nav|footer)[^>]*>.*?</\1>", "", html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"&nbsp;", " ", text)
        text = re.sub(r"&amp;", "&", text)
        text = re.sub(r"&lt;", "<", text)
        text = re.sub(r"&gt;", ">", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()


class WebTools:
    """Fast HTTP research tools for autonomous web operations."""

    def __init__(self, workspace_root: str | Path = "."):
        self.workspace_root = Path(workspace_root).resolve()

    def web_fetch(self, url: str, max_chars: int = 12000, timeout: int = 15) -> dict[str, Any]:
        """Fetch content from a web page and return clean markdown/text."""
        try:
            import httpx
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9,az;q=0.8",
            }
            with httpx.Client(follow_redirects=True, timeout=timeout, headers=headers) as client:
                resp = client.get(url)
                status = resp.status_code
                content_type = resp.headers.get("content-type", "")

                if "application/json" in content_type:
                    text = resp.text
                else:
                    text = _html_to_clean_text(resp.text)

                if len(text) > max_chars:
                    text = text[:max_chars] + f"\n\n[... Truncated, {len(text) - max_chars} characters omitted ...]"

                # Title extraction
                title_match = re.search(r"<title[^>]*>(.*?)</title>", resp.text, re.IGNORECASE)
                title = title_match.group(1).strip() if title_match else url

                return {
                    "url": url,
                    "status_code": status,
                    "title": title,
                    "content": text,
                    "success": status < 400,
                }
        except Exception as exc:
            return {
                "url": url,
                "status_code": 0,
                "title": "",
                "content": "",
                "error": f"Failed to fetch '{url}': {exc}",
                "success": False,
            }

    def web_search(self, query: str, max_results: int = 5) -> dict[str, Any]:
        """Search DuckDuckGo HTML search and return top search results."""
        try:
            import httpx
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            }
            encoded_query = urllib.parse.quote_plus(query)
            url = f"https://html.duckduckgo.com/html/?q={encoded_query}"

            with httpx.Client(follow_redirects=True, timeout=12, headers=headers) as client:
                resp = client.post("https://html.duckduckgo.com/html/", data={"q": query})
                html = resp.text

                # Extract search results from HTML
                results: list[dict[str, str]] = []
                # Find result snippets and links
                # Format typically: <a class="result__snippet" ...>...</a> and <a class="result__url" ...>...</a>
                snippets = re.findall(r'<a[^>]+class="result__snippet"[^>]*>(.*?)</a>', html, re.DOTALL)
                titles_urls = re.findall(r'<a[^>]+class="result__url"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', html, re.DOTALL)

                if not titles_urls:
                    # Generic anchor match
                    titles_urls = re.findall(r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', html, re.DOTALL)

                for i, (href, raw_title) in enumerate(titles_urls[:max_results]):
                    # Unwrap DuckDuckGo redirect link if present
                    actual_url = href
                    if "uddg=" in href:
                        try:
                            actual_url = urllib.parse.unquote(href.split("uddg=")[1].split("&")[0])
                        except Exception:
                            actual_url = href

                    clean_title = re.sub(r"<[^>]+>", "", raw_title).strip()
                    clean_snippet = re.sub(r"<[^>]+>", "", snippets[i]).strip() if i < len(snippets) else ""

                    results.append({
                        "title": clean_title or actual_url,
                        "url": actual_url,
                        "snippet": clean_snippet,
                    })

                return {
                    "query": query,
                    "results_count": len(results),
                    "results": results,
                    "success": True,
                }
        except Exception as exc:
            return {
                "query": query,
                "results_count": 0,
                "results": [],
                "error": f"Search failed: {exc}",
                "success": False,
            }

    def web_extract_links(self, url: str) -> dict[str, Any]:
        """Extract all outgoing links from a web page."""
        try:
            import httpx
            with httpx.Client(follow_redirects=True, timeout=10) as client:
                resp = client.get(url)
                links = list(set(re.findall(r'href=["\'](https?://[^"\']+)["\']', resp.text)))
                return {
                    "url": url,
                    "links_count": len(links),
                    "links": links[:50],
                    "success": True,
                }
        except Exception as exc:
            return {
                "url": url,
                "links": [],
                "error": str(exc),
                "success": False,
            }
