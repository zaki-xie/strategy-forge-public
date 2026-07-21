"""
Web Search Provider ABC
网络搜索服务提供商基类Abstract Base Class
=======================

Defines the pluggable-backend interface for web search and content extraction.
Providers register instances via ``PluginContext.register_web_search_provider()``;
the active one (selected via ``web.search_backend`` / ``web.extract_backend`` /
``web.backend`` in ``config.yaml``) services every ``web_search`` /
``web_extract`` tool call.
定义了用于网页搜索和内容提取的可插拔后端接口。  
提供者通过 ``PluginContext.register_web_search_provider()`` 注册实例；  
当前激活的后端（通过 ``config.yaml`` 中的 ``web.search_backend`` / ``web.extract_backend`` / ``web.backend`` 选择）
将为每次 ``web_search`` / ``web_extract`` 工具调用提供服务。

Providers live in ``<repo>/plugins/web/<name>/`` (built-in, auto-loaded as
``kind: backend``) or ``~/.hermes/plugins/web/<name>/`` (user, opt-in via
``plugins.enabled``).
提供程序位于 `<repo>/plugins/web/<name>/`（内置，自动加载为 `kind: backend`）
或 `~/.hermes/plugins/web/<name>/`（用户，通过 `plugins.enabled` 选择性启用）。

This ABC is the SINGLE plugin-facing surface for web providers — every
provider in the tree (brave-free, ddgs, searxng, exa, parallel, tavily,
firecrawl) implements it. The legacy in-tree ``tools.web_providers.base``
ABCs were deleted in PR #25182 along with the per-vendor inline helpers
in ``tools/web_tools.py``; the response-shape contract documented below
is preserved bit-for-bit so the tool wrapper does not have to translate.
这个ABC是面向网络服务提供商的唯一插件接口——树中的每个提供商
（brave-free、ddgs、searxng、exa、parallel、tavily、firecrawl）都实现了它。
在PR #25182中，原有的树内“tools.web_providers.base” ABC以及“tools/web_tools.py”中的各供应商内联辅助函数已被删除；
但下方所记录的响应形状契约将被原样保留，因此工具包装器无需进行转换。

Response shape (preserved from the legacy contract):

Search results::

    {
        "success": True,
        "data": {
            "web": [
                {"title": str, "url": str, "description": str, "position": int},
                ...
            ]
        }
    }

Extract results::

    {
        "success": True,
        "data": [
            {"url": str, "title": str, "content": str,
             "raw_content": str, "metadata": dict},
            ...
        ]
    }

On failure (either capability)::

    {"success": False, "error": str}
"""
# 用于延迟注解求值的包
# 例如def foo(x: list[int]) -> None:
# 会理解为def foo(x: "list[int]") -> None:
# 否则类似如下的自引用语法会报错
# class MyClass:
#    def method(self, other: MyClass) -> None:  # ❌ NameError: name 'MyClass' is not defined
from __future__ import annotations

import abc
import os
from typing import Any, Dict, List, Optional


def get_provider_env(name: str) -> str:
    """
    获取 Web 搜索提供者（如 Firecrawl、Tavily 等）所需的环境变量值。

    Resolves *name* via :func:`hermes_cli.config.get_env_value` (checks
    ``os.environ`` first, then ``~/.hermes/.env``) so credentials set
    through Hermes' config layer are visible even when they were never
    exported into the process environment — gateway sessions, delegate
    children, and subprocess agent runs (issue #40190). Falls back to a
    bare ``os.getenv`` when the config module is unavailable (stripped
    installs, early import contexts).

    读取顺序：
    1. 优先从操作系统环境变量（os.environ）读取。
    2. 若未找到，则从 Hermes 配置层的 .env 文件（由 get_env_path() 决定）读取。
    3. 若都未设置，返回空字符串。

    Returns the stripped value, or ``""`` when unset.

    返回:
        str: 变量值（去除首尾空白），若未设置则返回空字符串 ""。
    """
    val: Optional[str] = None
    try:
        from strategy_cli.config import get_env_value

        val = get_env_value(name)
    except Exception:  # noqa: BLE001 — config layer optional here
        val = None
    if val is None:
        val = os.getenv(name, "")
    return (val or "").strip()


# ---------------------------------------------------------------------------
# ABC
# ---------------------------------------------------------------------------


class WebSearchProvider(abc.ABC):
    """Abstract base class for a web search/extract backend.

    Subclasses must implement :meth:`is_available` and at least one of
    :meth:`search` / :meth:`extract`. The :meth:`supports_search` /
    :meth:`supports_extract` capability flags let the registry route each
    tool call to the right provider, and let multi-capability providers
    (Firecrawl, Tavily, Exa, …) advertise multiple capabilities from a
    single class.

    网页搜索/内容提取后端的抽象基类（Abstract Base Class）。

    所有具体的 Web 搜索提供者（如 Firecrawl、Tavily、Exa、SearXNG 等）
    都必须继承此类，并实现其抽象方法。

    核心职责：
        - 定义统一的接口（name, is_available, search, extract 等）
        - 通过 supports_search / supports_extract 声明自身能力
        - 提供 get_setup_schema 为交互式配置（hermes tools）提供元数据

    设计约束：
        - is_available() 必须轻量（无网络 I/O），在工具注册和界面渲染时频繁调用。
        - search() / extract() 的返回值必须遵循规定的 JSON 结构，
          失败时统一返回 {"success": False, "error": str}。
        - extract() 可以是同步或异步函数，调度器会自动检测并适配。
    """

    # @property
    # 把方法变成只读属性，像使用字段那样用它

    # @abc.abstractmethod
    #  必须被重写的方法

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """Stable short identifier used in ``web.search_backend`` /
        ``web.extract_backend`` / ``web.backend`` config keys.

        Lowercase, no spaces; hyphens permitted to preserve existing
        user-visible names. Examples: ``brave-free``, ``ddgs``,
        ``searxng``, ``firecrawl``.

        后端的稳定短标识符。

        用于在 ``web.search_backend`` / ``web.extract_backend`` / ``web.backend`` 使用。
        必须：
            - 全小写
            - 不含空格
            - 允许连字符（-）以兼容现有命名（如 brave-free, ddgs）

        示例："firecrawl", "tavily", "brave-free", "searxng"
        """

    @property
    def display_name(self) -> str:
        """Human-readable label shown in ``hermes tools``. Defaults to ``name``.
        
        在 hermes tools 界面中显示的人类可读名称。默认返回 name，子类可覆盖以提供更友好的展示名（如 "DuckDuckGo (ddgs)"）。
        """
        return self.name

    @abc.abstractmethod
    def is_available(self) -> bool:
        """Return True when this provider can service calls.

        Typically a cheap check (env var present, optional Python dep
        importable, instance URL set). Must NOT make network calls — this
        runs at tool-registration time and on every ``hermes tools`` paint.

        检查此后端是否可用（即能否正常服务调用）。

        典型实现：
            - 检查必需的环境变量是否存在（如 API Key）
            - 检查可选 Python 依赖是否可导入
            - 检查自托管实例 URL 是否配置

        重要约束：
            - 此方法在工具注册时及 hermes tools 界面渲染时会被频繁调用。
            - 必须非常轻量，**绝对不能发起网络请求**（如 HTTP 探活、OAuth 刷新）。
            - 仅做本地快速检查，若检查失败则返回 False。

        返回：
            bool: 可用返回 True，否则 False。
        """

    def supports_search(self) -> bool:
        """Return True if this provider implements :meth:`search`.
        
        声明此后端是否支持网页搜索（search 方法）。

        默认为 True，即假定所有后端都支持搜索。
        如果子类不支持搜索（例如某些后端只做内容提取），应覆盖返回 False。
        """
        return True

    def supports_extract(self) -> bool:
        """Return True if this provider implements :meth:`extract`.

        Both sync and async :meth:`extract` implementations are valid — the
        dispatcher detects coroutine functions via
        :func:`inspect.iscoroutinefunction` and awaits as needed. Sync
        implementations that perform blocking I/O (HTTP, SDK calls) should
        ideally wrap in :func:`asyncio.to_thread` at the call site; small
        providers can keep their sync shape and let the dispatcher handle
        threading.

        声明此后端是否支持内容提取（extract 方法）。

        默认为 False，子类若支持提取应覆盖返回 True。

        注意：
            - extract 方法既可以是同步函数，也可以是 async 协程。
              调度器会通过 inspect.iscoroutinefunction 检测并自动适配。
            - 如果是同步实现且包含阻塞 I/O（如 HTTP 请求），
              应在调用点用 asyncio.to_thread 包装，避免阻塞事件循环。
        """
        return False

    def search(self, query: str, limit: int = 5) -> Dict[str, Any]:
        """Execute a web search.

        Override when :meth:`supports_search` returns True. The default
        raises NotImplementedError; callers should gate on
        :meth:`supports_search` before calling.

        执行网页搜索。

        当 supports_search() 返回 True 时，子类必须覆盖此方法。
        默认实现抛出 NotImplementedError。

        Search results::
            {
                "success": True,
                "data": {
                    "web": [
                        {"title": str, "url": str, "description": str, "position": int},
                        ...
                    ]
                }
            }

        On failure (either capability)::
            {"success": False, "error": str}

         注意：
            调用方在调用前应通过 supports_search() 确认能力，但即使不检查，
            此方法也应安全返回错误字典而非抛出异常。
        """
        raise NotImplementedError(
            f"{self.name} does not support search (override supports_search)"
        )

    def extract(self, urls: List[str], **kwargs: Any) -> Any:
        """Extract content from one or more URLs.

        Override when :meth:`supports_extract` returns True. The default
        raises NotImplementedError; callers should gate on
        :meth:`supports_extract` before calling.

        Return shape: a list of result dicts matching what the legacy
        :func:`tools.web_tools.web_extract_tool` post-processing pipeline
        expects::

            [
                {
                    "url": str,
                    "title": str,
                    "content": str,
                    "raw_content": str,
                    "metadata": dict,           # optional
                    "error": str,               # optional, only on per-URL failure
                },
                ...
            ]

        Implementations MAY be ``async def`` — the dispatcher detects
        coroutines via :func:`inspect.iscoroutinefunction` and awaits.

        ``kwargs`` may carry forward-compat fields (``format``, ``include_raw``,
        ``max_chars``) — implementations should ignore unknown keys.

        从一个或多个 URL 提取网页内容。

        当 supports_extract() 返回 True 时，子类必须覆盖此方法。
        默认实现抛出 NotImplementedError。

        参数：
            urls (List[str]): 要提取的 URL 列表
            **kwargs: 向前兼容的扩展字段（如 format, include_raw, max_chars 等），
                      子类应忽略未知键。

        返回值格式（必须遵循）：
            成功时返回一个列表，每个元素为：
                {
                    "url": str,
                    "title": str,
                    "content": str,          # 清洗后的纯文本或 Markdown
                    "raw_content": str,      # 原始抓取内容（可选）
                    "metadata": dict,        # 额外元数据（可选）
                    "error": str,            # 若该 URL 提取失败时填写
                }
            整体失败（如 API 调用出错）可返回 {"success": False, "error": str}，
            但推荐在列表元素中标记错误，以保持部分成功。

        注意：
            - 此方法可以是 async def，调度器会自动适配。
            - 应妥善处理单个 URL 失败，不影响其他 URL 的提取。

        """
        raise NotImplementedError(
            f"{self.name} does not support extract (override supports_extract)"
        )

    def get_setup_schema(self) -> Dict[str, Any]:
        """Return provider metadata for the ``hermes tools`` picker.

        Used by ``hermes_cli/tools_config.py`` to inject this provider as a
        row in the Web Search / Web Extract picker. Shape::

            {
                "name": "Brave Search (Free)",
                "badge": "free",
                "tag": "No paid tier needed — uses Brave's free API.",
                "env_vars": [
                    {"key": "BRAVE_SEARCH_API_KEY",
                     "prompt": "Brave Search API key",
                     "url": "https://brave.com/search/api/"},
                ],
            }

        Default: minimal entry derived from ``display_name``. Override to
        expose API key prompts, badges, and instance URL fields.

        提供此后端的配置元数据，供 hermes tools 交互式设置向导使用。

        返回值结构：
            {
                "name": str,          # 显示名称
                "badge": str,         # 标签（如 "free", "paid"）
                "tag": str,           # 简短说明
                "env_vars": [         # 需要用户填写的环境变量列表
                    {
                        "key": str,   # 变量名
                        "prompt": str,# 显示给用户的提示
                        "url": str,   # 获取 API Key 的文档链接（可选）
                    },
                    ...
                ],
                "post_setup": str,    # 可选，安装后执行的命令标识（如安装 Python 包）
            }

        默认实现返回最简条目（仅包含 display_name）。
        子类应覆盖以提供详细的配置指引，尤其要列出必需的 env_vars。
        """
        return {
            "name": self.display_name,
            "badge": "",
            "tag": "",
            "env_vars": [],
        }
