"""Website access policy helpers for URL-capable tools.

This module loads a user-managed website blocklist from ~/.hermes/config.yaml
and optional shared list files. It is intentionally lightweight so web/browser
tools can enforce URL policy without pulling in the heavier CLI config stack.

Policy is cached in memory with a short TTL so config changes take effect
quickly without re-reading the file on every URL check.
网站访问策略助手（用于 URL 工具）

此模块从 ~/.hermes/config.yaml 中加载用户管理的网站屏蔽列表，
以及可选的共享列表文件。它设计为轻量级，以便 Web/浏览器工具在
执行 URL 请求前强制执行策略，而无需引入更重的 CLI 配置栈。

策略在内存中缓存，具有短 TTL（生存时间），以便配置更改能快速生效，
而无需在每次 URL 检查时重新读取文件。
"""

from __future__ import annotations

import fnmatch
import logging
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from strategy_cli.config import get_home

logger = logging.getLogger(__name__)

# 默认的网站屏蔽列表配置（当 config.yaml 中未配置时使用）
_DEFAULT_WEBSITE_BLOCKLIST = {
    "enabled": False,
    "domains": [],
    "shared_files": [],
}

# Cache: parsed policy + timestamp.  Avoids re-reading config.yaml on every
# URL check (a multi-URL extract with 50 pages would otherwise mean 51 YAML parses).
# 缓存配置：避免在每次 URL 检查时重新解析 config.yaml
# 例如，一个提取 50 个 URL 的操作原本会导致 51 次 YAML 解析
_CACHE_TTL_SECONDS = 30.0
_cache_lock = threading.Lock()
_cached_policy: Optional[Dict[str, Any]] = None # 缓存的策略字典
_cached_policy_path: Optional[str] = None       # 缓存对应的配置文件路径
_cached_policy_time: float = 0.0                # 缓存时间戳


def _get_default_config_path() -> Path:
    return get_home() / "config.yaml"


class WebsitePolicyError(Exception):
    """当网站策略文件格式错误时抛出。"""


def _normalize_host(host: str) -> str:
    """规范化主机名：转小写、去除首尾空白、去除末尾点号。"""
    return (host or "").strip().lower().rstrip(".")


def _normalize_rule(rule: Any) -> Optional[str]:
    """
    将用户输入的规则字符串规范化为可匹配的域名模式。

    处理规则：
        - 必须是字符串且非空
        - 跳过以 # 开头的注释
        - 如果包含 ://，提取主机名部分（忽略协议和路径）
        - 去除协议、路径、端口等，只保留域名
        - 去除开头的 www. （www.example.com → example.com）
        - 转换为小写

    返回规范化后的模式，或 None（无效规则）。
    """
    if not isinstance(rule, str):
        return None
    value = rule.strip().lower()
    if not value or value.startswith("#"):
        return None
    # 如果包含协议，只取主机名部分
    if "://" in value:
        parsed = urlparse(value)
        value = parsed.netloc or parsed.path
    # 去除端口、路径等（只保留域名）
    value = value.split("/", 1)[0].strip().rstrip(".")
    # 去除开头的 www.
    if value.startswith("www."):
        value = value[4:]
    return value or None


def _iter_blocklist_file_rules(path: Path) -> List[str]:
    """Load rules from a shared blocklist file.

    Missing or unreadable files log a warning and return an empty list
    rather than raising — a bad file path should not disable all web tools.
    从共享屏蔽列表文件中加载规则。

    文件格式：每行一个域名或模式，支持 # 注释。
    如果文件不存在或无法读取，记录警告并返回空列表（不会抛出异常），
    以免一个坏路径导致所有 Web 工具失效。
    """
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        logger.warning("Shared blocklist file not found (skipping): %s", path)
        return []
    except (OSError, UnicodeDecodeError) as exc:
        logger.warning("Failed to read shared blocklist file %s (skipping): %s", path, exc)
        return []

    rules: List[str] = []
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        normalized = _normalize_rule(stripped)
        if normalized:
            rules.append(normalized)
    return rules

# ============================================================================
# 策略加载（从 config.yaml）
# ============================================================================
def _load_policy_config(config_path: Optional[Path] = None) -> Dict[str, Any]:
    """
    从 config.yaml 加载网站屏蔽策略配置。

    配置位置：security.website_blocklist
    结构：
        security:
          website_blocklist:
            enabled: true/false
            domains:
              - example.com
              - *.evil.net
            shared_files:
              - ~/blocklist.txt

    若文件不存在或解析失败，返回默认配置（禁用状态）。
    """
    config_path = config_path or _get_default_config_path()
    if not config_path.exists():
        return dict(_DEFAULT_WEBSITE_BLOCKLIST)

    try:
        import yaml
    except ImportError:
        logger.debug("PyYAML not installed — website blocklist disabled")
        return dict(_DEFAULT_WEBSITE_BLOCKLIST)

    try:
        with open(config_path, encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
    except yaml.YAMLError as exc:
        raise WebsitePolicyError(f"Invalid config YAML at {config_path}: {exc}") from exc
    except OSError as exc:
        raise WebsitePolicyError(f"Failed to read config file {config_path}: {exc}") from exc
    if not isinstance(config, dict):
        raise WebsitePolicyError("config root must be a mapping")

    security = config.get("security", {})
    if security is None:
        security = {}
    if not isinstance(security, dict):
        raise WebsitePolicyError("security must be a mapping")

    website_blocklist = security.get("website_blocklist", {})
    if website_blocklist is None:
        website_blocklist = {}
    if not isinstance(website_blocklist, dict):
        raise WebsitePolicyError("security.website_blocklist must be a mapping")

    # 用用户配置覆盖默认值
    policy = dict(_DEFAULT_WEBSITE_BLOCKLIST)
    policy.update(website_blocklist)
    return policy

# ============================================================================
# 主要接口：加载策略（带缓存）
# ============================================================================
def load_website_blocklist(config_path: Optional[Path] = None) -> Dict[str, Any]:
    """Load and return the parsed website blocklist policy.

    Results are cached for ``_CACHE_TTL_SECONDS`` to avoid re-reading
    config.yaml on every URL check.  Pass an explicit ``config_path``
    to bypass the cache (used by tests).
    加载并返回解析后的网站屏蔽策略。

    结果缓存 _CACHE_TTL_SECONDS 秒，以避免在每次 URL 检查时重新读取 config.yaml。
    传入显式的 config_path 可绕过缓存（用于测试）。
    """
    global _cached_policy, _cached_policy_path, _cached_policy_time

    default_path = str(_get_default_config_path())
    resolved_path = str(config_path) if config_path else default_path
    now = time.monotonic()

    # 如果缓存仍然有效且路径相同，直接返回缓存
    if config_path is None:
        with _cache_lock:
            if (
                _cached_policy is not None
                and _cached_policy_path == resolved_path
                and (now - _cached_policy_time) < _CACHE_TTL_SECONDS
            ):
                return _cached_policy

    config_path = config_path or _get_default_config_path()
    policy = _load_policy_config(config_path)

    # 验证 domains 字段
    raw_domains = policy.get("domains", []) or []
    if not isinstance(raw_domains, list):
        raise WebsitePolicyError("security.website_blocklist.domains must be a list")

    # 验证 shared_files 字段
    raw_shared_files = policy.get("shared_files", []) or []
    if not isinstance(raw_shared_files, list):
        raise WebsitePolicyError("security.website_blocklist.shared_files must be a list")

    # 验证 enabled 字段
    enabled = policy.get("enabled", True)
    if not isinstance(enabled, bool):
        raise WebsitePolicyError("security.website_blocklist.enabled must be a boolean")

    # 构建最终规则列表（去重）
    rules: List[Dict[str, str]] = []
    seen: set[Tuple[str, str]] = set()

    # 从 domains 添加
    for raw_rule in raw_domains:
        normalized = _normalize_rule(raw_rule)
        if normalized and ("config", normalized) not in seen:
            rules.append({"pattern": normalized, "source": "config"})
            seen.add(("config", normalized))

    # 从 shared_files 添加
    for shared_file in raw_shared_files:
        if not isinstance(shared_file, str) or not shared_file.strip():
            continue
        path = Path(shared_file).expanduser()
        if not path.is_absolute():
            path = (get_home() / path).resolve()
        for normalized in _iter_blocklist_file_rules(path):
            key = (str(path), normalized)
            if key in seen:
                continue
            rules.append({"pattern": normalized, "source": str(path)})
            seen.add(key)

    result = {"enabled": enabled, "rules": rules}

    # Cache the result (only for the default path — explicit paths are tests)
    # 仅当使用默认路径时才缓存（显式路径通常用于测试）
    if config_path == _get_default_config_path():
        with _cache_lock:
            _cached_policy = result
            _cached_policy_path = resolved_path
            _cached_policy_time = now

    return result


def invalidate_cache() -> None:
    """强制下一次 check_website_access 调用重新读取配置文件。"""
    global _cached_policy
    with _cache_lock:
        _cached_policy = None

# ============================================================================
# 匹配逻辑
# ============================================================================
def _match_host_against_rule(host: str, pattern: str) -> bool:
    """
    检查主机名是否匹配某个模式（支持 * 通配符）。

    支持模式：
        - 精确匹配：example.com
        - 后缀通配：*.example.com（匹配子域名）
        - 前缀通配：*.evil（匹配 evil 及所有子域名，但要求 pattern 以 *. 开头）
    """
    if not host or not pattern:
        return False
    if pattern.startswith("*."):
        return fnmatch.fnmatch(host, pattern)
    return host == pattern or host.endswith(f".{pattern}")


def _extract_host_from_urlish(url: str) -> str:
    """从 URL 字符串中提取规范化主机名。

    支持带有协议和没有协议的输入（如 "example.com/path"）。
    """
    parsed = urlparse(url)
    host = _normalize_host(parsed.hostname or parsed.netloc)
    if host:
        return host

    if "://" not in url:
        schemeless = urlparse(f"//{url}")
        host = _normalize_host(schemeless.hostname or schemeless.netloc)
        if host:
            return host

    return ""

# ============================================================================
# 主入口：检查 URL 是否允许访问
# ============================================================================
def check_website_access(url: str, config_path: Optional[Path] = None) -> Optional[Dict[str, str]]:
    """Check whether a URL is allowed by the website blocklist policy.

    Returns ``None`` if access is allowed, or a dict with block metadata
    (``host``, ``rule``, ``source``, ``message``) if blocked.

    Never raises on policy errors — logs a warning and returns ``None``
    (fail-open) so a config typo doesn't break all web tools.  Pass
    ``config_path`` explicitly (tests) to get strict error propagation.

    检查 URL 是否被网站屏蔽策略允许访问。

    返回：
        - None：允许访问
        - dict：如果被阻止，返回包含阻止元数据的字典：
            {
                "url": str,
                "host": str,
                "rule": str,
                "source": str,
                "message": str
            }

    错误处理：
        - 默认策略错误时返回 None（允许访问，fail-open），以免配置错误导致所有工具失效。
        - 传入 config_path 时（测试用）会抛出 WebsitePolicyError 以便测试断言。
    """
    # Fast path: if no explicit config_path and the cached policy is disabled
    # or empty, skip all work (no YAML read, no host extraction).
    if config_path is None:
        with _cache_lock:
            if _cached_policy is not None and not _cached_policy.get("enabled"):
                return None

    host = _extract_host_from_urlish(url)
    if not host:
        return None

    try:
        policy = load_website_blocklist(config_path)
    except WebsitePolicyError as exc:
        if config_path is not None:
            raise  # Tests pass explicit paths — let errors propagate
        logger.warning("Website policy config error (failing open): %s", exc)
        return None
    except Exception as exc:
        logger.warning("Unexpected error loading website policy (failing open): %s", exc)
        return None

    if not policy.get("enabled"):
        return None

    for rule in policy.get("rules", []):
        pattern = rule.get("pattern", "")
        if _match_host_against_rule(host, pattern):
            logger.info("Blocked URL %s — matched rule '%s' from %s",
                        url, pattern, rule.get("source", "config"))
            return {
                "url": url,
                "host": host,
                "rule": pattern,
                "source": rule.get("source", "config"),
                "message": (
                    f"Blocked by website policy: '{host}' matched rule '{pattern}'"
                    f" from {rule.get('source', 'config')}"
                ),
            }
    return None
