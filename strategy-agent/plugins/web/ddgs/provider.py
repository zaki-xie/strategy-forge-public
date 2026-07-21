"""DuckDuckGo search — plugin form (via the ``ddgs`` package).

Subclasses the plugin-facing :class:`agent.web_search_provider.WebSearchProvider`.
The legacy in-tree module ``tools.web_providers.ddgs`` was removed in the
same commit that moved this code under ``plugins/``; this file is now the
canonical implementation.

The ``ddgs`` package is an optional dependency. ``is_available()`` reflects
whether the package is importable; the plugin still registers either way so
``hermes tools`` can prompt the user to install it.

DuckDuckGo search搜索插件
继承了面向插件的 :class:`agent.web_search_provider.WebSearchProvider`。

“ddgs”包是一个可选依赖项。“is_available()”用于判断该包是否可导入；
无论情况如何，插件都会进行注册，因此“hermes tools”仍可提示用户安装该包。

"""

from __future__ import annotations

import concurrent.futures as _cf
import logging
from typing import Any, Dict

from agent.web_search_provider import WebSearchProvider

logger = logging.getLogger(__name__)

# Overall wall-clock cap for a single ddgs search. The DDGS constructor's
# ``timeout`` only bounds individual HTTP requests; ddgs's multi-engine retry
# loop has no overall cap, so a slow/rate-limited DuckDuckGo response can hang
# the (single, shared) agent loop indefinitely and block every platform
# (#36776). Enforce a hard cap here via a worker thread.

# 单次ddgs搜索的总体时钟上限。
# DDGS构造器的“timeout”仅限制单个HTTP请求；
# 而ddgs的多引擎重试循环没有整体上限，因此缓慢或被限速的DuckDuckGo响应可能会无限期阻塞（单个共享）代理循环，
# 并导致所有平台均被阻断（#36776）。
# 此处通过工作线程强制实施硬性上限。
_SEARCH_TIMEOUT_SECS = 30


def _run_ddgs_search(query: str, safe_limit: int) -> list[dict[str, Any]]:
    """Run the blocking ddgs query and return normalized hits.

    Module-level (not a closure) so tests can patch it directly without
    spawning a real multi-second worker thread. ``DDGS(timeout=...)`` bounds
    each individual HTTP request; the overall wall-clock cap is enforced by
    the caller via a future timeout.

    运行阻塞的 ddgs 搜索查询，并返回规范化的搜索结果列表。

    此函数被设计为模块级函数（非闭包或嵌套函数），
    以便在单元测试中可以直接通过 mock.patch 替换它，
    避免在测试中产生真正的网络请求或长时间阻塞。

    DDGS 客户端的 timeout 参数（10秒）仅限制每个独立的 HTTP 请求，
    而整体搜索的墙钟时间上限由调用方通过 Future.result(timeout) 强制实施，
    从而避免因服务端响应缓慢而导致整个 Agent 循环被阻塞。

    参数:
        query (str): 搜索查询字符串。
        safe_limit (int): 要返回的最大结果数量。

    返回:
        list[dict[str, Any]]: 包含规范化搜索结果的列表，每个字典包含：
            - title (str): 结果标题
            - url (str): 结果链接
            - description (str): 结果描述/摘要
            - position (int): 从 1 开始的位置序号
    """
    from ddgs import DDGS  # type: ignore

    results: list[dict[str, Any]] = []
    # 创建 DDGS 客户端，每个 HTTP 请求超时 10 秒
    with DDGS(timeout=10) as client:
        # client.text 返回一个生成器/迭代器，产生搜索结果项
        # max_results 限制返回数量，但为防御性编程，仍显式 break
        for i, hit in enumerate(client.text(query, max_results=safe_limit)):
            if i >= safe_limit:
                break
            # 从结果项中提取 URL，优先 href 字段，其次 url 字段，最后为空字符串
            url = str(hit.get("href") or hit.get("url") or "")
            # 构建规范化条目，position 从 1 开始
            results.append(
                {
                    "title": str(hit.get("title", "")),
                    "url": url,
                    "description": str(hit.get("body", "")),
                    "position": i + 1,
                }
            )
    return results


class DDGSWebSearchProvider(WebSearchProvider):
    """DuckDuckGo HTML-scrape search provider.

    No API key needed. Rate limits are enforced server-side by DuckDuckGo;
    the provider surfaces ``DuckDuckGoSearchException`` and other ddgs errors
    as ``{"success": False, "error": ...}`` rather than raising.

    DuckDuckGo HTML 抓取搜索供应（基于 ddgs 包）。

    特点：
        - 无需 API Key，完全免费。
        - 仅支持搜索（不支持内容提取）。
        - 使用 ddgs 包进行搜索，该包通过抓取 DuckDuckGo 的 HTML 结果页工作。
        - 速率限制由 DuckDuckGo 服务端强制执行，本提供者将 ddgs 抛出的异常（如 DuckDuckGoSearchException）
          统一转换为 {"success": False, "error": ...} 格式返回，不向外抛出异常。

    设计细节：
        - is_available() 仅检测 ddgs 包是否可导入，无网络开销。
        - search() 通过线程池执行阻塞调用，并强制施加整体超时（30秒），
          防止因 DuckDuckGo 响应缓慢或限流导致 Agent 循环被永久阻塞。
        - 每次调用创建独立的单线程池，避免超时后无法取消的遗留任务阻塞后续搜索。
    """

    @property
    def name(self) -> str:
        """
        返回后端的稳定标识符 "ddgs"。

        用于配置文件引用（如 web.search_backend: "ddgs"）。
        """
        return "ddgs"

    @property
    def display_name(self) -> str:
        """
        返回在 hermes tools 界面中显示的人类可读名称。
        """
        return "DuckDuckGo (ddgs)"

    def is_available(self) -> bool:
        """Return True when the ``ddgs`` package is importable.

        Probes the import once; cheap because Python caches the import. Must
        NOT perform network I/O — runs at tool-registration time and on every
        ``hermes tools`` paint.

        检查 ddgs 包是否已安装。

        由于 ddgs 是可选依赖，只有安装后才能使用此后端。
        此方法在工具注册时和 hermes tools 界面渲染时被频繁调用，
        因此必须快速且不发起网络请求。

        返回:
            bool: 包已安装返回 True，否则 False。
        """
        try:
            import ddgs  # noqa: F401

            return True
        except ImportError:
            return False

    def supports_search(self) -> bool:
        """此后端支持搜索功能。"""
        return True

    def supports_extract(self) -> bool:
        """此后端不支持内容提取（仅搜索）。"""
        return False

    def search(self, query: str, limit: int = 5) -> Dict[str, Any]:
        """Execute a DuckDuckGo search and return normalized results.

        The synchronous ``ddgs`` call is run in a worker thread with a hard
        wall-clock timeout (``_SEARCH_TIMEOUT_SECS``) so a hung search cannot
        block the shared agent loop indefinitely (#36776).

        执行 DuckDuckGo 搜索并返回规范化的结果。

        实现要点：
            1. 再次确认 ddgs 包已安装，若未安装返回错误。
            2. 将同步阻塞的 _run_ddgs_search 提交到单线程线程池中执行。
            3. 使用 Future.result(timeout=30) 强制限制整体执行时间。
            4. 捕获 TimeoutError 并返回友好的超时错误信息。
            5. 捕获其他异常（如 ddgs 抛出的 DuckDuckGoSearchException）并返回错误。
            6. 最后关闭线程池（不等待），即使超时后任务仍在运行也不会影响后续搜索。

        超时处理说明：
            - ddgs 客户端的 timeout 参数仅控制单个 HTTP 请求，但 ddgs 内部可能有多轮重试，
              整体无上限。因此必须用外层超时保护。
            - 当超时发生时，正在运行的线程无法被强制取消，但通过每个调用新建独立线程池，
              并立即关闭（不等待），我们隔离了超时任务，使其不会阻塞后续搜索。

        参数:
            query (str): 搜索关键词。
            limit (int): 返回结果的最大数量（默认 5）。

        返回:
            Dict[str, Any]: 成功时返回 {"success": True, "data": {"web": [...]}}，
                            失败时返回 {"success": False, "error": str}。
        """
        # 再次检查 ddgs 包是否可用（防御性编程）
        try:
            import ddgs  # type: ignore  # noqa: F401 — availability probe
        except ImportError:
            return {
                "success": False,
                "error": "ddgs package is not installed — run `pip install ddgs`",
            }

        # DDGS().text yields at most `max_results` items; we cap defensively
        # in case the package ignores the hint.
        # 限制 safe_limit 至少为 1，且确保为整数
        safe_limit = max(1, int(limit))

        # A fresh single-worker pool per call (rather than a module-level one)
        # is intentional: on timeout the blocking ddgs call cannot be cancelled
        # and keeps running, so a shared pool would serialise every later search
        # behind that hung worker. A per-call pool isolates each search from a
        # previously-hung one.
        # 每个搜索调用创建独立的单线程线程池。
        # 设计意图：如果某个搜索超时，其线程无法被取消（会继续运行直到完成），
        # 使用共享线程池会导致该线程被占用，后续搜索排队等待，影响性能。
        # 每个调用独立池子，超时后立即关闭（不等待），让那个线程自生自灭，互不影响。
        pool = _cf.ThreadPoolExecutor(max_workers=1)
        try:
            # 提交阻塞搜索任务到线程池
            future = pool.submit(_run_ddgs_search, query, safe_limit)
            try:
                # 等待结果，强制超时 _SEARCH_TIMEOUT_SECS（30秒）
                web_results = future.result(timeout=_SEARCH_TIMEOUT_SECS)
            except _cf.TimeoutError:
                # 超时错误，记录警告并返回友好提示
                logger.warning(
                    "DDGS search timed out after %ds for query: %r",
                    _SEARCH_TIMEOUT_SECS, query,
                )
                return {
                    "success": False,
                    "error": (
                        f"DuckDuckGo search timed out after {_SEARCH_TIMEOUT_SECS}s — "
                        "DuckDuckGo may be rate-limiting or slow. Try again later "
                        "or switch to a different search provider."
                    ),
                }
        except Exception as exc:  # noqa: BLE001 — ddgs raises its own exceptions
            logger.warning("DDGS search error: %s", exc)
            return {"success": False, "error": f"DuckDuckGo search failed: {exc}"}
        finally:
            # Return immediately without joining the worker. On timeout the
            # already-running ddgs call can't be cancelled (cancel_futures only
            # affects not-yet-started work), so the worker runs to completion
            # on its own; it writes nothing shared, so leaking it is safe.
            # 关闭线程池，但不等待已提交的任务完成（wait=False）。
            # 如果超时发生，任务仍在运行，但我们不关心其结果，立即返回。
            # cancel_futures=True 会尝试取消尚未开始的任务，但对已在运行的任务无效。
            # 这样做可避免线程资源泄露，同时不会阻塞当前调用。
            pool.shutdown(wait=False, cancel_futures=True)
        # 成功：记录日志并返回规范化结果
        logger.info("DDGS search '%s': %d results (limit %d)", query, len(web_results), limit)
        return {"success": True, "data": {"web": web_results}}

    def get_setup_schema(self) -> Dict[str, Any]:
        """
        返回 hermes tools 配置向导所需的元数据。

        说明：
            - 该后端免费，无需 API Key，所以 env_vars 为空。
            - badge 标记为“free · no key · search only”提醒用户。
            - tag 给出简短说明。
            - post_setup 设为 "ddgs"，当用户选择此后端时，hermes tools
              会自动执行 pip install ddgs（通过 _run_post_setup 函数）。
        """
        return {
            "name": "DuckDuckGo (ddgs)",
            "badge": "free · no key · search only",
            "tag": "Search via the ddgs Python package — no API key (pair with any extract provider)",
            "env_vars": [],
            # Trigger `_run_post_setup("ddgs")` after the user picks this row
            # so the ddgs Python package gets pip-installed on first selection.
            "post_setup": "ddgs",
        }
