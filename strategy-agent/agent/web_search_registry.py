"""
Web Search Provider Registry
============================

Central map of registered web providers. Populated by plugins at import-time
via :meth:`PluginContext.register_web_search_provider`; consumed by the
``web_search`` and ``web_extract`` tool wrappers in :mod:`tools.web_tools` to
dispatch each call to the active backend.

Active selection
----------------
The active provider is chosen by configuration with this precedence:

1. ``web.search_backend`` / ``web.extract_backend``
   (per-capability override).
2. ``web.backend`` (shared fallback).
3. If exactly one capability-eligible provider is registered AND available,
   use it.
4. Legacy preference order — ``firecrawl`` → ``parallel`` → ``tavily`` →
   ``exa`` → ``searxng`` → ``brave-free`` → ``ddgs`` — filtered by
   availability. Matches the historic ``tools.web_tools._get_backend()``
   candidate order so installs that never set a config key keep landing
   on the same provider they did before the plugin migration.
5. Otherwise ``None`` — the tool surfaces a helpful error pointing at
   ``hermes tools``.

The capability filter (``supports_search`` / ``supports_extract``) is
applied at every step so a search-only provider (``brave-free``)
configured as ``web.extract_backend`` correctly falls through to an
extract-capable backend.

Web 搜索提供者注册表
============================

已注册的 Web 提供者的中心映射表。由插件在导入时通过 :meth:`PluginContext.register_web_search_provider` 填充；
由 :mod:`tools.web_tools` 中的 ``web_search`` 和 ``web_extract`` 工具包装器使用，将每次调用分派到活动的后端。

活动选择
----------------
活动提供者按以下优先级通过配置选择：

1. ``web.search_backend`` / ``web.extract_backend``（按能力覆盖）。
2. ``web.backend``（共享回退）。
3. 如果正好有一个已注册的且符合能力要求的提供者并且 ``is_available()`` 为 True，则使用它。
4. 遗留偏好顺序 —— ``firecrawl`` → ``parallel`` → ``tavily`` → ``exa`` → ``searxng`` → ``brave-free`` → ``ddgs`` —— 按可用性过滤。
   这与历史上的 ``tools.web_tools._get_backend()`` 候选顺序匹配，因此从未设置配置键的安装升级后仍会落在之前使用的同一提供者上。
5. 否则为 ``None`` —— 工具会显示一个有用的错误，指向 ``hermes tools``。

在每一步都应用能力过滤器（``supports_search`` / ``supports_extract``），
因此仅搜索的提供者（如 ``brave-free``）被配置为 ``web.extract_backend`` 时会正确地回退到支持提取的后端。
"""

from __future__ import annotations

import logging
import threading
from typing import Dict, List, Optional

from agent.web_search_provider import WebSearchProvider

logger = logging.getLogger(__name__)

# ============================================================================
# 全局注册表（线程安全）
# ============================================================================
# _providers 字典存储所有已注册的提供者，键为 provider.name（如 "ddgs"），值为实例。
# _lock 保证并发注册/查询时的线程安全。
_providers: Dict[str, WebSearchProvider] = {}
_lock = threading.Lock()


def register_provider(provider: WebSearchProvider) -> None:
    """Register a web search/extract provider.

    Re-registration (same ``name``) overwrites the previous entry and logs
    a debug message — makes hot-reload scenarios (tests, dev loops) behave
    predictably.

    注册一个 Web 搜索/提取提供者。

    如果同名提供者已存在，会覆盖之前的条目并记录调试日志。
    这种设计支持热重载（测试、开发循环）场景。

    参数:
        provider: 必须继承自 WebSearchProvider 的实例。

    异常:
        TypeError: 如果 provider 不是 WebSearchProvider 的子类实例。
        ValueError: 如果 provider.name 为空或不是有效字符串。
    """
    # 类型检查：确保传入的是正确的抽象基类实例
    if not isinstance(provider, WebSearchProvider):
        raise TypeError(
            f"register_provider() expects a WebSearchProvider instance, "
            f"got {type(provider).__name__}"
        )
    name = provider.name
    if not isinstance(name, str) or not name.strip():
        raise ValueError("Web provider .name must be a non-empty string")
    
    # 线程安全地更新全局字典
    # 用name参数绑定对应的WebSearchProvider类型
    with _lock:
        existing = _providers.get(name)
        _providers[name] = provider
    
    # 记录日志（覆盖或新增）
    if existing is not None:
        logger.debug(
            "Web provider '%s' re-registered (was %r)",
            name, type(existing).__name__,
        )
    else:
        logger.debug(
            "Registered web provider '%s' (%s)",
            name, type(provider).__name__,
        )


def list_providers() -> List[WebSearchProvider]:
    """Return all registered providers, sorted by name.
    
    返回所有已注册的提供者列表，按名称排序。
    """
    with _lock:
        items = list(_providers.values())
    return sorted(items, key=lambda p: p.name)


def get_provider(name: str) -> Optional[WebSearchProvider]:
    """Return the provider registered under *name*, or None.
    
    根据名称获取已注册的提供者，不存在则返回 None。
    """
    if not isinstance(name, str):
        return None
    with _lock:
        return _providers.get(name.strip())


# ---------------------------------------------------------------------------
# Active-provider resolution
# ---------------------------------------------------------------------------


def _read_config_key(*path: str) -> Optional[str]:
    """Resolve a dotted config key from ``config.yaml``. Returns None on miss.
    
    从 config.yaml 中读取点分隔的配置键值，若不存在则返回 None。

    *path 是可变参数，允许传入多个字符串，它们按顺序构成一个“路径”。
    例如：
        _read_config_key("web", "search_backend")
        将尝试访问 config["web"]["search_backend"]。

    在函数内部，path 是一个元组，例如 ("web", "search_backend")。
    循环 for segment in path 中，segment 依次为 "web" 和 "search_backend"，
    逐级深入字典结构。

    如果中间某一级不是字典（或不存在），则返回 None。
    如果最终值是非空字符串，则返回去除首尾空格的该字符串；否则返回 None。

    任何异常（如文件不存在、YAML 解析错误等）都会被捕获并记录调试日志，
    并返回 None，确保调用方不会因配置问题而崩溃。

    参数:
        *path: 一个或多个字符串，表示配置键的层级路径。

    返回:
        Optional[str]: 配置值（非空字符串），或 None。
    """
    try:
        from strategy_cli.config import load_config

        cfg = load_config() # 加载完整的配置字典（带缓存）
        cur = cfg
        for segment in path:
            # segment 是当前层级的键名，如 "web" 或 "search_backend"
            if not isinstance(cur, dict):
                return None
            cur = cur.get(segment)
        # 如果最终值是非空字符串则返回，否则返回 None
        if isinstance(cur, str) and cur.strip():
            return cur.strip()
    except Exception as exc:
        logger.debug("Could not read config %s: %s", ".".join(path), exc)
    return None


# Legacy preference order — preserves behaviour for users who set no
# ``web.backend`` / ``web.<capability>_backend`` config key at all. Matches
# the historic candidate order in :func:`tools.web_tools._get_backend`
# (paid providers first so existing paid setups don't get downgraded to
# a free tier on upgrade). Filtered by ``is_available()`` at walk time so
# we don't surface a provider the user has no credentials for.
# 遗留偏好顺序（Legacy preference order）
# 当用户没有设置任何 web.backend 或 web.search_backend 时使用此顺序。
# 按优先级从高到低排列（付费服务优先，避免现有付费用户降级到免费层）。
_LEGACY_PREFERENCE = (
    "firecrawl",
    "parallel",
    "tavily",
    "exa",
    "searxng",
    "brave-free",
    "ddgs",
)


def _resolve(configured: Optional[str], *, capability: str) -> Optional[WebSearchProvider]:
    """Resolve the active provider for a capability ("search" | "extract").

    Resolution rules (in order):

    1. **Explicit config wins, ignoring availability.** If
       ``web.{capability}_backend`` or ``web.backend`` names a registered
       provider that supports *capability*, return it even if its
       :meth:`is_available` returns False — the dispatcher will surface a
       precise "X_API_KEY is not set" error to the user instead of silently
       routing somewhere else. Matches legacy
       :func:`tools.web_tools._get_backend` behavior for configured names.

    2. **Single-provider shortcut.** When only one registered provider
       supports *capability* AND ``is_available()`` reports True, return it.

    3. **Legacy preference walk, filtered by availability.** Walk the
       :data:`_LEGACY_PREFERENCE` order (firecrawl → parallel → tavily →
       exa → searxng → brave-free → ddgs) looking for a provider whose
       ``supports_<capability>()`` is True AND whose ``is_available()`` is
       True. Matches the historic ``tools.web_tools._get_backend()``
       candidate order so users with credentials but no explicit config
       key keep landing on the same provider as pre-migration. This is
       the path that fires when no config key is set — pick the
       highest-priority backend the user actually has credentials for.

    Returns None when no provider is configured AND no available provider
    matches the legacy preference; the dispatcher then returns a "set up a
    provider" error to the user.

    解析指定能力（"search" 或 "extract"）的活动提供者。

    解析规则（按优先级依次尝试）：
    1. 显式配置优先（即使 is_available() 返回 False）
       - 如果配置了 web.{capability}_backend 或 web.backend，
         且该名称注册了提供者且支持该能力，则直接返回。
       - 此时不检查 is_available()，以便向下游传递精确的错误信息（如 "API Key未设置"），
         而不是静默切换到其他后端。
    2. 单提供者快捷方式
       - 如果只有一个已注册的提供者支持该能力且 is_available() 为 True，
         直接返回它。
    3. 遗留偏好顺序（按 _LEGACY_PREFERENCE 顺序）过滤 is_available()
       - 依次检查每个名称，返回第一个支持该能力且 is_available() 为 True 的提供者。
       - 这保证了老用户（未设置配置键）升级后仍能落到他们之前使用的后端。

    若以上均未命中，返回 None，由上层工具返回友好的错误提示。

    参数:
        configured: 配置中指定的后端名称（可能为 None）。
        capability: "search" 或 "extract"。

    返回:
        解析出的 WebSearchProvider 实例，或 None。
    """
    # 快照当前注册表，避免在解析过程中被修改
    with _lock:
        snapshot = dict(_providers)

    # 辅助函数：判断提供者是否支持指定能力
    def _capable(p: WebSearchProvider) -> bool:
        if capability == "search":
            return bool(p.supports_search())
        if capability == "extract":
            return bool(p.supports_extract())
        return False

    # 辅助函数：安全调用 is_available()，捕获异常并返回 False
    def _is_available_safe(p: WebSearchProvider) -> bool:
        """Wrap ``is_available()`` so a buggy provider doesn't kill resolution."""
        try:
            return bool(p.is_available())
        except Exception as exc:  # noqa: BLE001
            logger.debug("provider %s.is_available() raised %s", p.name, exc)
            return False

    # 1. Explicit config wins — return regardless of is_available() so the
    #    user gets a precise downstream error message rather than a silent
    #    backend switch. Matches _get_backend() in web_tools.py.
    # --- 规则1：显式配置优先 ---
    if configured:
        provider = snapshot.get(configured)
        if provider is not None and _capable(provider):
            return provider
        if provider is None:
            logger.debug(
                "web backend '%s' configured but not registered; falling back",
                configured,
            )
        else:
            logger.debug(
                "web backend '%s' configured but does not support '%s'; falling back",
                configured, capability,
            )

    # 2. + 3. Fallback path — filter by availability so we don't surface
    #    a provider the user has no credentials for. Without this filter,
    #    a registered-but-unconfigured provider could end up "active" on
    #    a fresh install with no API keys at all.
    # --- 规则2：单提供者快捷方式 ---
    # 收集所有支持该能力且可用的提供者
    eligible = [
        p for p in snapshot.values()
        if _capable(p) and _is_available_safe(p)
    ]
    if len(eligible) == 1:
        return eligible[0]

    # --- 规则3：遗留偏好顺序 ---
    # 按偏好顺序排查和返回
    for legacy in _LEGACY_PREFERENCE:
        provider = snapshot.get(legacy)
        if (
            provider is not None
            and _capable(provider)
            and _is_available_safe(provider)
        ):
            return provider

    return None

# 需要依赖hermes的庞大plugin系统，非核心功能，仅用于检查插件是否被禁用，暂时注释
def _disabled_web_plugin_for(configured: Optional[str] = None, *, capability: Optional[str] = None) -> Optional[str]:
    """Return the plugin key of a *disabled* bundled web plugin that would
    have provided the configured backend, or None.

    When a user sets ``web.extract_backend: firecrawl`` (or the search
    equivalent) but also lists ``web-firecrawl`` in ``plugins.disabled``,
    the provider never registers and the dispatcher would otherwise emit a
    misleading "No web extract provider configured. Set web.extract_backend
    to ..." error — even though the backend IS configured correctly. The
    real fix is to re-enable the plugin. This helper detects that case so
    the dispatcher can point the user at the actual cause (issue #40190
    follow-up: pi314's disabled-plugin symptom).

    Pass ``capability`` ("search" | "extract") to resolve the configured
    name straight from ``config.yaml`` (``web.<capability>_backend`` →
    ``web.backend``). This is more reliable than the resolved backend the
    dispatcher fell back to, since a disabled provider fails the
    ``_is_backend_available`` gate and the dispatcher silently drops to
    the shared default. An explicit ``configured`` name still wins when
    given.

    Matching is by convention: bundled web plugins live under the
    ``web/<vendor>`` key with the provider ``name`` differing only in
    hyphen/underscore (``brave-free`` provider ⇄ ``web/brave_free`` key,
    ``firecrawl`` ⇄ ``web/firecrawl``). We normalize both sides before
    comparing so every bundled provider is covered without hardcoding a
    per-vendor table.

    检测是否因为插件被禁用而导致配置的后端无法使用。

    场景：用户设置了 web.extract_backend: firecrawl，但对应的插件 firecrawl 在 plugins.disabled 中被禁用。
    此时提供者不会被注册，导致调度器提示“未配置后端”，而实际上用户已经配置了。
    此函数通过检查插件管理器，识别出被禁用的插件正是配置中指定的那个，
    从而让上层工具给出精确的错误信息：“你的插件被禁用了，请启用它”。

    匹配规则：按照约定，内置 Web 插件位于 web/<vendor> 键下，
    提供者名称与 vendor 名称仅在下划线/连字符上略有不同（如 brave-free ↔ web/brave_free）。
    因此通过规范化字符串（转为小写，替换 - 为 _）进行比较。

    参数:
        configured: 可选，直接指定的后端名称；若不提供，则根据 capability 从配置中读取。
        capability: "search" 或 "extract"，用于读取对应的配置键。

    返回:
        如果检测到被禁用的插件，返回其插件键（如 "web/firecrawl"），否则返回 None。
    """
    # def _norm(s: str) -> str:
    #     return s.strip().lower().replace("-", "_")

    # # 如果未显式提供 configured，则从配置中读取
    # if not configured and capability in ("search", "extract"):
    #     configured = (
    #         _read_config_key("web", f"{capability}_backend")
    #         or _read_config_key("web", "backend")
    #     )
    # if not configured:
    #     return None

    # want = _norm(configured)
    # try:
    #     from strategy_cli.plugins import get_plugin_manager

    #     pm = get_plugin_manager()
    #     # 遍历所有已加载的插件
    #     for key, loaded in pm._plugins.items():
    #         if not isinstance(key, str) or not key.startswith("web/"):
    #             continue
    #         if loaded.enabled:
    #             continue
    #         if loaded.error != "disabled via config":
    #             continue
    #         vendor = key.split("/", 1)[1]
    #         if _norm(vendor) == want:
    #             return key
    # except Exception as exc:  # noqa: BLE001 — diagnostics are best-effort
    #     logger.debug("disabled-web-plugin lookup failed: %s", exc)
    return None


def get_active_search_provider() -> Optional[WebSearchProvider]:
    """Resolve the currently-active web search provider.

    Reads ``web.search_backend`` (preferred) or ``web.backend`` (shared
    fallback) from config.yaml; falls back per the module docstring.

    解析当前可用的搜索提供者。

    读取顺序：
    1. web.search_backend（优先）
    2. web.backend（共享后备）
    3. 自动降级（见 _resolve 的规则2和3）

    返回解析出的提供者或 None。
    """
    explicit = _read_config_key("web", "search_backend") or _read_config_key("web", "backend")
    return _resolve(explicit, capability="search")


def get_active_extract_provider() -> Optional[WebSearchProvider]:
    """Resolve the currently-active web extract provider.

    Reads ``web.extract_backend`` (preferred) or ``web.backend`` (shared
    fallback) from config.yaml; falls back per the module docstring.

    解析当前可用的提取提供者。

    读取顺序：
    1. web.extract_backend（优先）
    2. web.backend（共享后备）
    3. 自动降级（见 _resolve 的规则2和3）

    返回解析出的提供者或 None。
    """
    explicit = _read_config_key("web", "extract_backend") or _read_config_key("web", "backend")
    return _resolve(explicit, capability="extract")


def _reset_for_tests() -> None:
    """Clear the registry. **Test-only.

    清空注册表。仅供测试使用。
    **"""
    with _lock:
        _providers.clear()
