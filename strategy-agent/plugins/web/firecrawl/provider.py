"""Firecrawl web search + extract — standalone, no Hermes-specific dependencies.

Uses direct API key (FIRECRAWL_API_KEY) or self-hosted URL (FIRECRAWL_API_URL).
Does NOT depend on tools.web_tools, tools.lazy_deps, or any gateway logic.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Dict, List, Optional
from strategy_cli.config import get_env_value

from agent.web_search_provider import WebSearchProvider

# 导入已经移植的安全模块
from tools.url_safety import is_safe_url
from tools.website_policy import check_website_access

logger = logging.getLogger(__name__)

# 尝试导入 firecrawl SDK，如果未安装则报错
try:
    from firecrawl import Firecrawl
except ImportError:
    raise ImportError(
        "firecrawl-py is not installed. Please install it: pip install firecrawl-py"
    )


# ============================================================================
# 简化的客户端获取（直接基于环境变量）
# ============================================================================

def _get_firecrawl_client() -> Firecrawl:
    """Create a Firecrawl client using credentials from env/config layer."""
    api_key = (get_env_value("FIRECRAWL_API_KEY") or "").strip()
    api_url = (get_env_value("FIRECRAWL_API_URL") or "").strip().rstrip("/")

    if not api_key and not api_url:
        raise ValueError(
            "Firecrawl not configured: set FIRECRAWL_API_KEY (cloud) or "
            "FIRECRAWL_API_URL (self-hosted) in .env or environment."
        )

    kwargs: Dict[str, str] = {}
    if api_key:
        kwargs["api_key"] = api_key
    if api_url:
        kwargs["api_url"] = api_url

    return Firecrawl(**kwargs)


# ============================================================================
# 响应规范化（简化版）
# ============================================================================

def _normalize_result_list(values: Any) -> List[Dict[str, Any]]:
    if not isinstance(values, list):
        return []
    normalized: List[Dict[str, Any]] = []
    for item in values:
        if isinstance(item, dict):
            normalized.append(item)
        elif hasattr(item, "model_dump"):
            try:
                normalized.append(item.model_dump())
            except Exception:
                pass
    return normalized


def _extract_web_search_results(response: Any) -> List[Dict[str, Any]]:
    if isinstance(response, dict):
        data = response.get("data")
        if isinstance(data, list):
            return _normalize_result_list(data)
        if isinstance(data, dict):
            web = _normalize_result_list(data.get("web"))
            if web:
                return web
            results = _normalize_result_list(data.get("results"))
            if results:
                return results
        web = _normalize_result_list(response.get("web"))
        if web:
            return web
        results = _normalize_result_list(response.get("results"))
        if results:
            return results
    elif hasattr(response, "web"):
        return _normalize_result_list(getattr(response, "web", []))
    return []


def _extract_scrape_payload(scrape_result: Any) -> Dict[str, Any]:
    if isinstance(scrape_result, dict):
        data = scrape_result.get("data")
        if isinstance(data, dict):
            return data
        return scrape_result
    if hasattr(scrape_result, "model_dump"):
        try:
            return scrape_result.model_dump().get("data", {})
        except Exception:
            pass
    return {}


# ============================================================================
# Provider 类
# ============================================================================

class FirecrawlWebSearchProvider(WebSearchProvider):
    @property
    def name(self) -> str:
        return "firecrawl"

    @property
    def display_name(self) -> str:
        return "Firecrawl"

    def is_available(self) -> bool:
        """Return True if FIRECRAWL_API_KEY or FIRECRAWL_API_URL is set."""
        return bool(get_env_value("FIRECRAWL_API_KEY") or get_env_value("FIRECRAWL_API_URL"))

    def supports_search(self) -> bool:
        return True

    def supports_extract(self) -> bool:
        return True

    def search(self, query: str, limit: int = 5) -> Dict[str, Any]:
        # 打断检查暂时移除
        # try:
        #     from tools.interrupt import is_interrupted
        #     if is_interrupted():
        #         return {"success": False, "error": "Interrupted"}
        # except ImportError:
        #     pass

        logger.info("Firecrawl search: '%s' (limit=%d)", query, limit)
        client = _get_firecrawl_client()
        try:
            response = client.search(query=query, limit=limit)
            web_results = _extract_web_search_results(response)
            logger.info("Firecrawl: found %d search results", len(web_results))
            return {"success": True, "data": {"web": web_results}}
        except Exception as exc:
            logger.warning("Firecrawl search error: %s", exc)
            return {"success": False, "error": f"Firecrawl search failed: {exc}"}

    async def extract(self, urls: List[str], **kwargs: Any) -> List[Dict[str, Any]]:
        # try:
        #     from tools.interrupt import is_interrupted
        # except ImportError:
        #     def is_interrupted():
        #         return False

        # if is_interrupted():
        #     return [{"url": u, "error": "Interrupted", "title": ""} for u in urls]

        format = kwargs.get("format")
        formats = ["markdown"] if format == "markdown" else ["html"] if format == "html" else ["markdown", "html"]

        results: List[Dict[str, Any]] = []
        client = _get_firecrawl_client()

        for url in urls:
            # if is_interrupted():
            #     results.append({"url": url, "error": "Interrupted", "title": ""})
            #     continue

            # 网站策略检查
            blocked = check_website_access(url)
            if blocked:
                logger.info("Blocked web_extract for %s by rule %s", blocked["host"], blocked["rule"])
                results.append({
                    "url": url,
                    "title": "",
                    "content": "",
                    "error": blocked["message"],
                    "blocked_by_policy": {
                        "host": blocked["host"],
                        "rule": blocked["rule"],
                        "source": blocked["source"],
                    },
                })
                continue

            try:
                logger.info("Firecrawl scraping: %s", url)
                try:
                    scrape_result = await asyncio.wait_for(
                        asyncio.to_thread(
                            client.scrape,
                            url=url,
                            formats=formats,
                        ),
                        timeout=60,
                    )
                except asyncio.TimeoutError:
                    logger.warning("Firecrawl scrape timed out for %s", url)
                    results.append({
                        "url": url,
                        "title": "",
                        "content": "",
                        "error": "Scrape timed out after 60s. Try browser_navigate instead.",
                    })
                    continue

                scrape_payload = _extract_scrape_payload(scrape_result)
                metadata = scrape_payload.get("metadata", {})
                content_markdown = scrape_payload.get("markdown")
                content_html = scrape_payload.get("html")

                if not isinstance(metadata, dict):
                    metadata = {}

                title = metadata.get("title", "")
                final_url = metadata.get("sourceURL", url)

                # 重定向后安全检查
                if not is_safe_url(final_url):
                    logger.info("Blocked redirected web_extract for unsafe final URL: %s", final_url)
                    results.append({
                        "url": final_url,
                        "title": title,
                        "content": "",
                        "raw_content": "",
                        "error": "Blocked: URL targets a private or internal network address",
                    })
                    continue

                final_blocked = check_website_access(final_url)
                if final_blocked:
                    logger.info("Blocked redirected web_extract for %s by rule %s",
                                final_blocked["host"], final_blocked["rule"])
                    results.append({
                        "url": final_url,
                        "title": title,
                        "content": "",
                        "raw_content": "",
                        "error": final_blocked["message"],
                        "blocked_by_policy": {
                            "host": final_blocked["host"],
                            "rule": final_blocked["rule"],
                            "source": final_blocked["source"],
                        },
                    })
                    continue


                if format == "markdown" and content_markdown:
                    chosen_content = content_markdown
                elif format == "html" and content_html:
                    chosen_content = content_html
                elif content_markdown:
                    chosen_content = content_markdown
                elif content_html:
                    chosen_content = content_html
                else:
                    chosen_content = ""

                results.append({
                    "url": final_url,
                    "title": title,
                    "content": chosen_content,
                    "raw_content": chosen_content,
                    "metadata": metadata,
                })

            except Exception as scrape_err:
                logger.debug("Firecrawl scrape failed for %s: %s", url, scrape_err)
                results.append({
                    "url": url,
                    "title": "",
                    "content": "",
                    "raw_content": "",
                    "error": str(scrape_err),
                })

        #print(f"[DEBUG] Firecrawl extract results: type={type(results)}, len={len(results)}")
        return results

    def get_setup_schema(self) -> Dict[str, Any]:
        return {
            "name": "Firecrawl",
            "badge": "paid",
            "tag": "Full search + extract. Requires FIRECRAWL_API_KEY (cloud) or FIRECRAWL_API_URL (self-hosted).",
            "env_vars": [
                {"key": "FIRECRAWL_API_KEY", "prompt": "Firecrawl API key", "url": "https://docs.firecrawl.dev/"},
                {"key": "FIRECRAWL_API_URL", "prompt": "Self-hosted Firecrawl URL (optional)"},
            ],
        }