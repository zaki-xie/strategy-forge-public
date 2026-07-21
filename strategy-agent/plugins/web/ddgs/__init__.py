"""DuckDuckGo search plugin — bundled, auto-loaded.

Backed by the community ``ddgs`` Python package which scrapes DDG's HTML
results page. No API key required, but the package itself must be installed
(it's an optional dep — gated via :meth:`is_available`).

DuckDuckGo 搜索插件——内置并自动加载。
由社区开发的 ``ddgs`` Python 包用于抓取 DDG 的 HTML 结果页面。
无需 API 密钥，但需要先安装该包（它是一个可选依赖项，可通过 :meth:`is_available` 检查是否可用）。
"""

from __future__ import annotations

from plugins.web.ddgs.provider import DDGSWebSearchProvider


def register(ctx) -> None:
    """Register the DDGS provider with the plugin context.
    在插件上下文中注册DDGS提供程序。
    """
    ctx.register_web_search_provider(DDGSWebSearchProvider())
