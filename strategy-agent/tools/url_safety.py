"""URL safety checks — blocks requests to private/internal network addresses.

Prevents SSRF (Server-Side Request Forgery) where a malicious prompt or
skill could trick the agent into fetching internal resources like cloud
metadata endpoints (169.254.169.254), localhost services, or private
network hosts.

The check can be globally disabled via ``security.allow_private_urls: true``
in config.yaml for environments where DNS resolves external domains to
private/benchmark-range IPs (OpenWrt routers, corporate proxies, VPNs
that use 198.18.0.0/15 or 100.64.0.0/10).  Even when disabled, cloud
metadata hostnames (metadata.google.internal, 169.254.169.254) are
**always** blocked — those are never legitimate agent targets.

Limitations (documented, not fixable at pre-flight level):
  - DNS rebinding (TOCTOU): an attacker-controlled DNS server with TTL=0
    can return a public IP for the check, then a private IP for the actual
    connection. Fixing this requires connection-level validation (e.g.
    Python's Champion library or an egress proxy like Stripe's Smokescreen).
  - Redirect-based bypass is mitigated by httpx event hooks that re-validate
    each redirect target in vision_tools, gateway platform adapters, and
    media cache helpers. Web tools use third-party SDKs (Firecrawl/Tavily)
    where redirect handling is on their servers.

URL 安全检查模块 —— 阻止对私有/内网地址的请求。

防止 SSRF（服务器端请求伪造）攻击：恶意提示词或技能可能诱使 Agent
获取内网资源，如云元数据端点（169.254.169.254）、本地服务或私有网络主机。

该检查可通过 config.yaml 中的 security.allow_private_urls: true 全局禁用，
适用于 DNS 将外部域名解析为私有/基准测试范围 IP 的环境（如 OpenWrt 路由器、
企业代理、使用 198.18.0.0/15 或 100.64.0.0/10 的 VPN）。
即使禁用，云元数据主机名（metadata.google.internal、169.254.169.254）
也**始终**被阻止——它们绝不是合法的 Agent 目标。

局限性（在预检层面无法修复）：
  - DNS 重绑定（TOCTOU）：攻击者控制的 DNS 服务器可设置 TTL=0，
    在检查时返回公网 IP，在实际连接时返回私有 IP。
    修复此问题需要连接级验证（如 Python 的 Champion 库或 egress 代理）。
  - 基于重定向的绕过已通过 httpx 事件钩子缓解，在 vision_tools、
    gateway 平台适配器和 media cache 助手中重新验证每个重定向目标。
    Web 工具使用第三方 SDK（Firecrawl/Tavily），重定向处理在其服务器端。
"""

import ipaddress
import logging
import os
import socket
import asyncio
import re
from typing import Any, Optional
from urllib.parse import parse_qsl, quote, unquote, urljoin, urlparse, urlsplit, urlunsplit

from utils import is_truthy_value

logger = logging.getLogger(__name__)


def normalize_url_for_request(url: str) -> str:
    """Return an ASCII-safe HTTP URL for Hermes-owned URL tools.

    Browsers and HTTP clients expect URIs, but users and models often provide
    IRIs such as ``https://wttr.in/Köln``.  Preserve URL syntax and existing
    percent escapes while encoding non-ASCII host/path/query/fragment text.
    This is intentionally for URL tool inputs only; arbitrary shell commands
    must not be rewritten.

    将用户/模型提供的 URL 转换为 ASCII 安全的 HTTP URL。

    浏览器和 HTTP 客户端期望 ASCII URI，但用户和模型经常提供 IRI，
    如 https://wttr.in/Köln。此函数在保留 URL 语法和现有百分号转义的同时，
    对非 ASCII 的主机名/路径/查询/片段进行编码。
    仅用于 URL 工具输入，不得用于任意 shell 命令。

    处理场景：
        - 非 ASCII 主机名（如 "例.com"）→ IDNA 编码为 "xn--..."
        - 非 ASCII 路径/查询/片段 → 百分号编码
        - 模型偶尔输出的畸形 URL，如 "https:// docs.example"（scheme 后有多余空格）
    """
    if not isinstance(url, str):
        return url

    raw = url.strip()
    if not raw:
        return raw

    # Models sometimes emit otherwise valid URLs with whitespace between the
    # scheme separator and authority (``https:// docs.example``). That position
    # is never meaningful in HTTP(S) URLs, and repairing it before parsing keeps
    # web tools from failing on a formatting artifact while leaving path/query
    # whitespace to the normal percent-encoding path below.
    # 修复模型输出中 scheme 后多余空格的问题（如 "https:// docs.example"）
    # 这种格式在 HTTP(S) URL 中永无意义，修复后再解析可避免工具失败
    raw = re.sub(r"^([A-Za-z][A-Za-z0-9+.-]*://)\s+", r"\1", raw)

    try:
        parsed = urlsplit(raw)
    except ValueError:
        return raw

    # 仅处理 HTTP/HTTPS 协议
    if parsed.scheme.lower() not in {"http", "https"}:
        return raw

    netloc = parsed.netloc
    hostname = parsed.hostname
    if hostname:
        # 非 ASCII 主机名使用 IDNA 编码（国际化域名转 ASCII）
        try:
            ascii_host = hostname.encode("idna").decode("ascii")
        except UnicodeError:
            ascii_host = hostname
        if ascii_host != hostname:
            netloc = netloc.replace(hostname, ascii_host, 1)

    # 路径/查询/片段的百分号编码（保留安全字符）
    path = quote(parsed.path, safe="/%:@!$&'()*+,;=")
    query = quote(parsed.query, safe="/%:@!$&'()*+,;=?")
    fragment = quote(parsed.fragment, safe="/%:@!$&'()*+,;=?")

    return urlunsplit((parsed.scheme, netloc, path, query, fragment))


# Query parameter names that are unambiguously credential-bearing. Kept
# deliberately narrow: bare English words that double as normal page facets
# (``code`` on promo/challenge pages, ``key``/``auth``/``session``/``sig`` as
# search or routing params) are intentionally EXCLUDED to avoid blocking
# ordinary browsing. Prefix-based token redaction (``is_safe_url``) still
# catches recognizable vendor key shapes; this set is the belt-and-suspenders
# for opaque secrets that carry an explicit credential-named parameter.
# ============================================================================
# 敏感查询参数检测
# ============================================================================

# 明确包含凭证的查询参数名列表。刻意保持窄范围：
# 普通英文单词（如 code、key、auth、session、sig）容易被误判为页面参数，
# 因此**故意排除**，避免阻止正常浏览。
# 前缀式令牌红名单（在 is_safe_url 中）仍能捕获可识别的厂商密钥形态；
# 此集合用于捕获显式携带凭证名的非透明密钥。
_SENSITIVE_QUERY_PARAM_NAMES = frozenset({
    "access_token",
    "api_key",
    "apikey",
    "auth_token",
    "authorization",
    "awsaccesskeyid",
    "client_secret",
    "credential",
    "credentials",
    "jwt",
    "password",
    "passwd",
    "secret",
    "session_id",
    "signature",
    "token",
    "x_amz_security_token",
    "x_amz_signature",
    "x-amz-security-token",
    "x-amz-signature",
})


def sensitive_query_param_name(url: str) -> Optional[str]:
    """Return the first sensitive query parameter name in ``url``, if any.

    Used before handing URLs to third-party fetch/browser backends. Prefix-based
    token redaction catches known credential shapes; this catches opaque magic
    links, OAuth codes, signed URL signatures, and custom ``?token=...`` values
    that do not have a recognizable vendor prefix.
    检查 URL 的查询参数中是否包含敏感凭证类参数名。
    用于在将 URL 传递给第三方抓取/浏览器后端之前的预检。
    前缀式令牌红名单能捕获已知凭证形态；此函数用于捕获无厂商前缀的
    非透明密钥（如 OAuth code、签名 URL、自定义 ?token=...）。
    """
    if not isinstance(url, str) or "?" not in url:
        return None
    try:
        parsed = urlsplit(url.strip())
    except ValueError:
        return None
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.query:
        return None
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        if value and unquote(key).lower() in _SENSITIVE_QUERY_PARAM_NAMES:
            return key
    return None


def has_sensitive_query_params(url: str) -> bool:
    """Return True when ``url`` carries likely credential-bearing query params.
    
    检查 URL 是否携带可能包含凭证的查询参数。
    """
    return sensitive_query_param_name(url) is not None

# Hostnames that should always be blocked regardless of IP resolution
# or any config toggle.  These are cloud metadata endpoints that an
# attacker could use to steal instance credentials.
# ============================================================================
# 始终拦截的黑名单（安全底线，不可绕过）
# ============================================================================

# 始终应拦截的主机名，无论 IP 解析结果或配置开关如何。
# 这些是云元数据端点，攻击者可利用其窃取实例凭证。
_BLOCKED_HOSTNAMES = frozenset({
    "metadata.google.internal",
    "metadata.goog",
})

# IPs and networks that should always be blocked regardless of the
# allow_private_urls toggle.  These are cloud metadata / credential
# endpoints — the #1 SSRF target — and the link-local range where
# they all live.
#
# IPv4-mapped IPv6 variants are included because DNS resolvers may
# return ``::ffff:x.x.x.x`` for IPv4-only hosts, and Python's
# ipaddress module treats these as distinct from the plain IPv4
# address (they won't match ``ip in frozenset`` or ``ip in network``).
# 始终应拦截的 IP 和网段，无论 allow_private_urls 开关如何。
# 这些是云元数据/凭证端点——SSRF 的首要目标，以及它们所在的链路本地范围。
# 包含 IPv4-mapped IPv6 变体，因为 DNS 解析器可能返回 ::ffff:x.x.x.x 形式的
# IPv4 映射地址，而 ipaddress 模块将其视为独立的 IPv6 地址。
_ALWAYS_BLOCKED_IPS = frozenset({
    ipaddress.ip_address("169.254.169.254"),  # AWS/GCP/Azure/DO/Oracle metadata
    ipaddress.ip_address("169.254.170.2"),     # AWS ECS task metadata (task IAM creds)
    ipaddress.ip_address("169.254.169.253"),   # Azure IMDS wire server
    ipaddress.ip_address("fd00:ec2::254"),     # AWS metadata (IPv6)
    ipaddress.ip_address("100.100.100.200"),   # Alibaba Cloud metadata
    # IPv4-mapped IPv6 variants — same endpoints reachable via ::ffff:x.x.x.x
    ipaddress.ip_address("::ffff:169.254.169.254"),
    ipaddress.ip_address("::ffff:169.254.170.2"),
    ipaddress.ip_address("::ffff:169.254.169.253"),
    ipaddress.ip_address("::ffff:100.100.100.200"),
})
_ALWAYS_BLOCKED_NETWORKS = (
    ipaddress.ip_network("169.254.0.0/16"),    # Entire link-local range (no legit agent target)
    ipaddress.ip_network("::ffff:169.254.0.0/112"), # IPv4-mapped link-local range
)

# Exact HTTPS hostnames allowed to resolve to private/benchmark-space IPs.
# This is intentionally narrow: QQ media downloads can legitimately resolve
# to 198.18.0.0/15 behind local proxy/benchmark infrastructure.
# 允许解析到私有/基准测试空间 IP 的 HTTPS 主机名白名单。
# 刻意保持窄范围：QQ 媒体下载可合法解析到本地代理/基准测试基础设施内的 198.18.0.0/15。
_TRUSTED_PRIVATE_IP_HOSTS = frozenset({
    "multimedia.nt.qq.com.cn",
})

# 100.64.0.0/10 (CGNAT / Shared Address Space, RFC 6598) is NOT covered by
# ipaddress.is_private — it returns False for both is_private and is_global.
# Must be blocked explicitly. Used by carrier-grade NAT, Tailscale/WireGuard
# VPNs, and some cloud internal networks.
# 100.64.0.0/10（CGNAT / 共享地址空间，RFC 6598）不被 ipaddress.is_private 覆盖，
# 必须显式阻止。用于运营商级 NAT、Tailscale/WireGuard VPN 和一些云内部网络。
_CGNAT_NETWORK = ipaddress.ip_network("100.64.0.0/10")

# ---------------------------------------------------------------------------
# Global toggle: allow private/internal IP resolution
# ---------------------------------------------------------------------------
# Cached after first read so we don't hit the filesystem on every URL check.
# ============================================================================
# 全局开关：允许私有 IP 解析
# ============================================================================
# 首次读取后缓存，避免每次 URL 检查都访问文件系统。
_allow_private_resolved = False
_cached_allow_private: bool = False


def _global_allow_private_urls() -> bool:
    """Return True when the user has opted out of private-IP blocking.

    Checks (in priority order):
    1. ``HERMES_ALLOW_PRIVATE_URLS`` env var  (``true``/``1``/``yes``)
    2. ``security.allow_private_urls`` in config.yaml
    3. ``browser.allow_private_urls`` in config.yaml  (legacy / backward compat)

    Result is cached for the process lifetime.
    返回用户是否已选择退出私有 IP 阻止（即允许访问私有地址）。

    检查优先级：
    1. HERMES_ALLOW_PRIVATE_URLS 环境变量（true/1/yes）
    2. config.yaml 中的 security.allow_private_urls
    3. config.yaml 中的 browser.allow_private_urls（旧版兼容）

    结果在进程生命周期内缓存。
    """
    global _allow_private_resolved, _cached_allow_private
    if _allow_private_resolved:
        return _cached_allow_private

    _allow_private_resolved = True
    _cached_allow_private = False  # safe default

    # 1. Env var override (highest priority)
     # 1. 环境变量覆盖（最高优先级）
    env_val = os.getenv("HERMES_ALLOW_PRIVATE_URLS", "").strip().lower()
    if env_val in {"true", "1", "yes"}:
        _cached_allow_private = True
        return _cached_allow_private
    if env_val in {"false", "0", "no"}:
        # Explicit false — don't fall through to config
        # 显式 false —— 不回退到配置文件
        return _cached_allow_private

    # 2. Config file
    try:
        from strategy_cli.config import read_raw_config
        cfg = read_raw_config()
        # security.allow_private_urls (preferred)
        sec = cfg.get("security", {})
        if isinstance(sec, dict) and is_truthy_value(
            sec.get("allow_private_urls"), default=False
        ):
            _cached_allow_private = True
            return _cached_allow_private
        # browser.allow_private_urls (legacy fallback)
        browser = cfg.get("browser", {})
        if isinstance(browser, dict) and is_truthy_value(
            browser.get("allow_private_urls"), default=False
        ):
            _cached_allow_private = True
            return _cached_allow_private
    except Exception:
        # Config unavailable (e.g. tests, early import) — keep default
        pass

    return _cached_allow_private


def _reset_allow_private_cache() -> None:
    """Reset the cached toggle — only for tests.
    
    重置缓存开关——仅用于测试。
    """
    global _allow_private_resolved, _cached_allow_private
    _allow_private_resolved = False
    _cached_allow_private = False

# ============================================================================
# IP 检查核心逻辑
# ============================================================================
def _is_blocked_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Return True if the IP should be blocked for SSRF protection.
    
    返回该 IP 是否应被 SSRF 防护阻止。

    检查包括：
        - 私有地址（is_private）
        - 环回地址（is_loopback）
        - 链路本地地址（is_link_local）
        - 保留地址（is_reserved）
        - 组播地址（is_multicast）
        - 未指定地址（is_unspecified）
        - CGNAT 范围（100.64.0.0/10）

    特殊处理：IPv4-mapped IPv6 地址（::ffff:x.x.x.x）应检查其嵌入的 IPv4 地址。
    """
    # IPv4-mapped IPv6 addresses (``::ffff:x.x.x.x``) should be checked
    # by their embedded IPv4 address, not as IPv6
    # IPv4-mapped IPv6 地址：检查其嵌入的 IPv4 地址
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        embedded_ip = ip.ipv4_mapped
        return (embedded_ip.is_private or embedded_ip.is_loopback or
                embedded_ip.is_link_local or embedded_ip.is_reserved or
                embedded_ip.is_multicast or embedded_ip.is_unspecified or
                embedded_ip in _CGNAT_NETWORK)

    # Standard IPv4/IPv6 address checking
    # 标准 IPv4/IPv6 地址检查
    if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
        return True
    if ip.is_multicast or ip.is_unspecified:
        return True
    # CGNAT range not covered by is_private
    # CGNAT 范围不被 is_private 覆盖
    if ip in _CGNAT_NETWORK:
        return True
    return False

# ============================================================================
# 安全底线检查（不可绕过）
# ============================================================================
def is_always_blocked_url(url: str) -> bool:
    """Return True when the URL targets an always-blocked endpoint.

    This is the security floor — cloud metadata IPs / hostnames
    (169.254.169.254, metadata.google.internal, ECS task metadata, etc.)
    that have no legitimate agent use regardless of backend, routing, or
    the ``allow_private_urls`` toggle.  Used by callers that bypass the
    full ``is_safe_url`` check for their own reasons (e.g. hybrid cloud
    browser routing to a local Chromium sidecar for private URLs) and
    still need to enforce the non-negotiable floor before letting the
    request proceed.

    Returns True (= blocked) on:
      - Hostnames in ``_BLOCKED_HOSTNAMES``
      - IPs / networks in ``_ALWAYS_BLOCKED_IPS`` / ``_ALWAYS_BLOCKED_NETWORKS``
      - URLs whose hostname resolves to any of the above

    Returns False (= not in the always-blocked floor) on:
      - Benign public / private / loopback URLs (whether or not they'd
        be blocked by the ordinary SSRF check)
      - DNS-resolution failures for non-sentinel hostnames (these are
        someone else's problem — the caller's ordinary fail-closed path
        will catch them if applicable)
      - Parse errors (caller decides fail-open vs fail-closed)

    Intentionally narrower than ``is_safe_url``: only blocks the sentinel
    set, not ordinary private addresses.  Callers that want the full
    SSRF check should still use ``is_safe_url``.

    检查 URL 是否指向始终被拦截的端点（安全底线）。

    这是安全下限——云元数据 IP/主机名（169.254.169.254、metadata.google.internal、
    ECS 任务元数据等）无论后端、路由或 allow_private_urls 开关如何都无合法 Agent 用途。
    用于那些因自身原因绕过完整 is_safe_url 检查的调用方（如混合云浏览器路由到本地
    Chromium sidecar 处理私有 URL），但仍需在放行请求前强制执行不可协商的安全底线。

    返回 True（= 被拦截）：
        - 主机名在 _BLOCKED_HOSTNAMES 中
        - IP 在 _ALWAYS_BLOCKED_IPS / _ALWAYS_BLOCKED_NETWORKS 中
        - URL 的主机名解析到上述任何地址

    返回 False（= 不在始终拦截的底线上）：
        - 良性公网/私有/环回 URL（无论是否会被普通 SSRF 检查拦截）
        - 非哨兵主机名的 DNS 解析失败（由调用方处理）
        - 解析错误（调用方决定 fail-open 还是 fail-closed）

    刻意比 is_safe_url 更窄：仅拦截哨兵集合，而非普通私有地址。
    需要完整 SSRF 检查的调用方仍应使用 is_safe_url。
    """
    try:
        parsed = urlparse(url)
        hostname = (parsed.hostname or "").strip().lower().rstrip(".")
        if not hostname:
            return False

        # Blocked-hostname check fires regardless of DNS resolution
        # 拦截主机名检查（不依赖 DNS 解析）
        if hostname in _BLOCKED_HOSTNAMES:
            logger.warning(
                "Blocked request to internal hostname (always-blocked floor): %s",
                hostname,
            )
            return True

        # Literal IP → check directly against the always-blocked set
        # 字面量 IP → 直接检查是否在始终拦截集合中
        try:
            ip = ipaddress.ip_address(hostname)
        except ValueError:
            ip = None

        if ip is not None:
            if ip in _ALWAYS_BLOCKED_IPS or any(
                ip in net for net in _ALWAYS_BLOCKED_NETWORKS
            ):
                logger.warning(
                    "Blocked request to cloud metadata address "
                    "(always-blocked floor): %s",
                    hostname,
                )
                return True
            return False

        # Hostname → resolve and check every answer.  DNS failure is NOT
        # always-blocked (caller's ordinary path handles that).
        # 主机名 → 解析并检查每个结果。DNS 失败不算始终拦截（由调用方处理）
        try:
            addr_info = socket.getaddrinfo(
                hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM
            )
        except socket.gaierror:
            return False

        for _family, _, _, _, sockaddr in addr_info:
            ip_str = sockaddr[0]
            if '%' in ip_str:
                ip_str = ip_str.split('%')[0]
            try:
                resolved = ipaddress.ip_address(ip_str)
            except ValueError:
                logger.warning("Unparseable IP address %r for hostname %s — skipping address", sockaddr[0], hostname)
                continue
            if resolved in _ALWAYS_BLOCKED_IPS or any(
                resolved in net for net in _ALWAYS_BLOCKED_NETWORKS
            ):
                logger.warning(
                    "Blocked request to cloud metadata address "
                    "(always-blocked floor): %s -> %s",
                    hostname,
                    ip_str,
                )
                return True

        return False

    except Exception as exc:
        # Parse failures or unexpected errors — don't claim the URL is
        # always-blocked.  Caller decides what to do with a malformed URL.
        logger.debug("is_always_blocked_url error for %s: %s", url, exc)
        return False


def _allows_private_ip_resolution(hostname: str, scheme: str) -> bool:
    """Return True when a trusted HTTPS hostname may bypass IP-class blocking.
    
    当受信任的 HTTPS 主机名可绕过 IP 类阻止时返回 True。
    """
    return scheme == "https" and hostname in _TRUSTED_PRIVATE_IP_HOSTS


def is_safe_url(url: str) -> bool:
    """Return True if the URL target is not a private/internal address.

    Resolves the hostname to an IP and checks against private ranges.
    Fails closed: DNS errors and unexpected exceptions block the request.

    When ``security.allow_private_urls`` is enabled (or the env var
    ``HERMES_ALLOW_PRIVATE_URLS=true``), private-IP blocking is skipped.
    Cloud metadata endpoints (169.254.169.254, metadata.google.internal)
    remain blocked regardless — they are never legitimate agent targets.

    检查 URL 目标是否为安全的公网地址（非私有/内网地址）。

    解析主机名为 IP，检查是否在私有范围内。
    **默认拒绝（fail closed）**：DNS 错误和意外异常都会阻止请求。

    当 security.allow_private_urls 启用（或环境变量 HERMES_ALLOW_PRIVATE_URLS=true）
    时，跳过私有 IP 阻止。但云元数据端点（169.254.169.254、metadata.google.internal）
    仍被阻止——它们绝不是合法的 Agent 目标。
    """
    try:
        parsed = urlparse(url)
        hostname = (parsed.hostname or "").strip().lower().rstrip(".")
        scheme = (parsed.scheme or "").strip().lower()
        if scheme not in {"http", "https"}:
            logger.warning("Blocked request — unsupported URL scheme: %s", scheme or "<empty>")
            return False
        if not hostname:
            return False

        # Block known internal hostnames — ALWAYS, even with toggle on
        # 拦截已知内部主机名 —— 始终拦截，即使开关打开
        if hostname in _BLOCKED_HOSTNAMES:
            logger.warning("Blocked request to internal hostname: %s", hostname)
            return False

        # Check the global toggle AFTER blocking metadata hostnames
        # 检查全局开关（在拦截元数据主机名之后）
        allow_all_private = _global_allow_private_urls()

        allow_private_ip = _allows_private_ip_resolution(hostname, scheme)

        # Try to resolve and check IP
        # 尝试解析并检查 IP
        try:
            addr_info = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
        except socket.gaierror:
            # DNS resolution failed — fail closed. If DNS can't resolve it,
            # the HTTP client will also fail, so blocking loses nothing.
            # DNS 解析失败 —— 默认拒绝。如果 DNS 无法解析，HTTP 客户端也会失败，
            # 因此阻止不会损失任何东西。
            logger.warning("Blocked request — DNS resolution failed for: %s", hostname)
            return False

        for family, _, _, _, sockaddr in addr_info:
            ip_str = sockaddr[0]
            if '%' in ip_str:
                ip_str = ip_str.split('%')[0]
            try:
                ip = ipaddress.ip_address(ip_str)
            except ValueError:
                # Still unparseable after scope ID strip — fail closed
                # 剥离 scope ID 后仍无法解析 —— 默认拒绝
                logger.warning("Blocked request — unparseable IP address %r for hostname %s", sockaddr[0], hostname)
                return False

            # Always block cloud metadata IPs and link-local, even with toggle on
            # 始终拦截云元数据 IP 和链路本地地址，即使开关打开
            if ip in _ALWAYS_BLOCKED_IPS or any(ip in net for net in _ALWAYS_BLOCKED_NETWORKS):
                logger.warning(
                    "Blocked request to cloud metadata address: %s -> %s",
                    hostname, ip_str,
                )
                return False

            if not allow_all_private and not allow_private_ip and _is_blocked_ip(ip):
                logger.warning(
                    "Blocked request to private/internal address: %s -> %s",
                    hostname, ip_str,
                )
                return False

        if allow_all_private:
            logger.debug(
                "Allowing private/internal resolution (security.allow_private_urls=true): %s",
                hostname,
            )
        elif allow_private_ip:
            logger.debug(
                "Allowing trusted hostname despite private/internal resolution: %s",
                hostname,
            )

        return True

    except Exception as exc:
        # Fail closed on unexpected errors — don't let parsing edge cases
        # become SSRF bypass vectors
        logger.warning("Blocked request — URL safety check error for %s: %s", url, exc)
        return False


async def async_is_safe_url(url: str) -> bool:
    """Same rules as :func:`is_safe_url`, but run the DNS work off the event loop.

    ``socket.getaddrinfo`` can block; call this from async code paths (gateway,
    ``web_extract_tool``, vision download hooks) instead of ``is_safe_url``.

    与 is_safe_url 相同的规则，但将 DNS 工作放到事件循环外执行。

    socket.getaddrinfo 可能阻塞；在异步代码路径（gateway、web_extract_tool、
    vision download hooks）中调用此函数而不是 is_safe_url。
    """
    return await asyncio.to_thread(is_safe_url, url)


def redirect_target_from_response(response: Any) -> Optional[str]:
    """Return the redirect target visible from inside an httpx response hook.

    In ``httpx.AsyncClient`` response event hooks, ``response.next_request`` is
    frequently ``None`` even for a genuine redirect (it is populated later by
    the redirect-following machinery). Relying on ``next_request`` alone means
    an SSRF redirect guard silently never fires: a public URL that 302s to
    ``http://169.254.169.254/`` gets followed anyway. The ``Location`` header,
    however, is already present on the response, so resolve the target from it
    first (handling relative Locations via ``urljoin``) and only fall back to
    ``next_request`` when no ``Location`` header is set.

    从 httpx 响应钩子中提取重定向目标 URL。

    在 httpx.AsyncClient 响应事件钩子中，即使发生真正的重定向，
    response.next_request 也经常为 None（由重定向追踪机制稍后填充）。
    仅依赖 next_request 意味着 SSRF 重定向防护可能静默失效：
    一个公网 URL 302 到 http://169.254.169.254/ 仍会被跟随。
    但 Location 头在响应时已存在，因此首先从该头解析目标（处理相对路径），
    仅当未设置 Location 头时回退到 next_request。
    """
    if not getattr(response, "is_redirect", False):
        return None

    headers = getattr(response, "headers", {}) or {}
    location = headers.get("location")
    if location:
        return urljoin(str(getattr(response, "url", "")), str(location))

    next_request = getattr(response, "next_request", None)
    if next_request:
        return str(next_request.url)

    return None
