"""Managed scope — IT-pushed, user-immutable config & env layer.

A system-level directory (default ``/etc/hermes``, root-owned and not
user-writable) supplies ``config.yaml`` and ``.env`` values that WIN over the
user's ``~/.hermes/config.yaml`` and ``~/.hermes/.env`` on a per-leaf-key basis.

This is DISTINCT from ``hermes_cli.config.is_managed()`` / ``HERMES_MANAGED``,
which is a coarse package-manager write-lock (declarative-distro / formula
installs). That lock blocks all mutation; this layer injects specific immutable
values. The two are independent and may coexist.

v1 enforcement is filesystem permissions only — see
``docs/design/managed-scope.md`` §7. v1 is Linux/POSIX-first; ``get_managed_dir()``
is the single seam for adding macOS / Windows native locations later.

Attribution: do not reference any third-party product by name in this file.

--------
Managed scope — IT-pushed, user-immutable config & env layer.

管理范围（Managed Scope）—— IT 部门推送、用户不可变的配置与环境变量层。

系统级目录（默认为 /etc/hermes，由 root 拥有且用户不可写）提供 config.yaml 和 .env 值，
这些值在“叶子键”级别上覆盖用户自己的 ~/.hermes/config.yaml 和 ~/.hermes/.env。

注意：此机制不同于 hermes_cli.config.is_managed() / HERMES_MANAGED，
后者是一个粗粒度的包管理器写入锁（用于声明式发行版/配方安装）。
该锁阻止所有修改；而本层注入特定的不可变值。两者相互独立，可以共存。

v1 实现仅依赖文件系统权限（见 docs/design/managed-scope.md §7）。
v1 首先支持 Linux/POSIX；get_managed_dir() 是将来添加 macOS/Windows 原生位置的唯一接缝。

归因：此文件中不引用任何第三方产品名称。
"""
from __future__ import annotations

import copy
import logging
import os
import threading
from pathlib import Path
from typing import Dict, Optional

import yaml

logger = logging.getLogger(__name__)

# POSIX default. Other-platform locations are a deliberate v2 item; when added,
# they belong ONLY inside get_managed_dir().
# POSIX 默认路径。其他平台的位置是 v2 的明确目标；添加时，只应放在 get_managed_dir() 内部。
_DEFAULT_MANAGED_DIR = Path("/etc/hermes")

# 缓存锁和保护两个缓存字典
_CACHE_LOCK = threading.Lock()
# path_key -> (mtime_ns, size, parsed)
_CONFIG_CACHE: Dict[str, tuple] = {}
_ENV_CACHE: Dict[str, tuple] = {}


def _under_pytest() -> bool:
    """True when running inside the test suite.

    Used to ignore the system default ``/etc/hermes`` during tests so a real
    managed scope on a developer/CI box can't leak policy into the suite. Tests
    that exercise managed scope set ``HERMES_MANAGED_DIR`` explicitly, which is
    still honored (the override path below runs before this guard takes effect).

    检测当前是否在 pytest 测试套件中运行。

    用于在测试期间忽略系统默认的 /etc/hermes，防止开发机或 CI 上的真实管理范围策略泄漏到测试中。
    明确设置了 HERMES_MANAGED_DIR 的测试仍会生效（因为覆盖路径优先于本检查）。
    """
    return "PYTEST_CURRENT_TEST" in os.environ


def get_managed_dir() -> Optional[Path]:
    """Resolve the managed-scope directory, or None when no scope is present.

    Resolution (highest priority first):
      1. ``$HERMES_MANAGED_DIR`` — deployment/bootstrap path override (IT-only;
         never persisted to any .env). Honored only when set to a non-empty value
         AND the directory exists.
      2. ``/etc/hermes`` — POSIX default, when it exists. Ignored under pytest so
         a real system managed scope can't leak into the test suite.

    A non-existent directory at either tier resolves to None (no managed scope),
    which is the common case and must be cheap + side-effect-free.

    解析管理范围目录，如果不存在管理范围则返回 None。

    解析优先级（从高到低）：
      1. $HERMES_MANAGED_DIR —— 部署/引导路径覆盖（仅 IT 使用，绝不持久化到任何 .env）。
         仅当设置为非空值且目录存在时才生效。
      2. /etc/hermes —— POSIX 默认路径，当它存在时生效。在 pytest 下忽略，防止真实系统管理范围泄露到测试。

    目录不存在时返回 None（无管理范围），这是常见情况，且必须轻量、无副作用。
    """
    override = os.environ.get("HERMES_MANAGED_DIR", "").strip()
    if override:
        p = Path(override)
        return p if p.is_dir() else None
    if _under_pytest():
        return None
    return _DEFAULT_MANAGED_DIR if _DEFAULT_MANAGED_DIR.is_dir() else None


def invalidate_managed_cache() -> None:
    """Drop cached managed config/env. For tests and post-edit reloads.
    
    丢弃已缓存的管理配置和环境变量。用于测试和编辑后重新加载
    """
    with _CACHE_LOCK:
        _CONFIG_CACHE.clear()
        _ENV_CACHE.clear()


def _cached_read(path: Path, cache: Dict[str, tuple], parse):
    """Shared (mtime_ns, size)-keyed read. Returns a deepcopy of the parsed value.

    Returns ``None`` when the file is absent or fails to parse (fail-open). A
    parse failure is logged LOUDLY — the admin needs to know their policy isn't
    being applied — but never raises, so a malformed managed file can't brick
    startup.

    共享的缓存读取函数，基于 (mtime_ns, size) 键值缓存。

    返回解析值的深拷贝。文件不存在或解析失败时返回 None（打开失败，fail-open）。
    解析失败会记录强烈警告日志 —— 管理员需要知道其策略未被应用 —— 但从不抛出异常，因此格式错误的管理文件不会阻止启动。
    """
    try:
        st = path.stat()
    except OSError:
        return None  # absent
    key = (st.st_mtime_ns, st.st_size)
    path_key = str(path)
    with _CACHE_LOCK:
        hit = cache.get(path_key)
        if hit is not None and hit[:2] == key:
            return copy.deepcopy(hit[2])
    try:
        with open(path, encoding="utf-8") as f:
            parsed = parse(f)
    except Exception as exc:  # noqa: BLE001 — fail-open, but LOUD
        logger.warning(
            "managed scope: failed to parse %s: %s — IGNORING this managed file. "
            "Admin policy from this file is NOT being applied. Fix and restart.",
            path,
            exc,
        )
        return None
    with _CACHE_LOCK:
        cache[path_key] = (key[0], key[1], copy.deepcopy(parsed))
    return parsed


def load_managed_config() -> dict:
    """Parsed managed config.yaml, or {} when absent/malformed (fail-open).
    
    加载管理范围的 config.yaml，如果不存在或格式错误则返回 {}（失败打开）。

    解析结果会缓存并深拷贝返回。
    """
    managed_dir = get_managed_dir()
    if managed_dir is None:
        return {}
    parsed = _cached_read(
        managed_dir / "config.yaml",
        _CONFIG_CACHE,
        lambda f: yaml.safe_load(f) or {},
    )
    return parsed if isinstance(parsed, dict) else {}


def load_managed_env() -> Dict[str, str]:
    """Parsed managed .env (KEY=VALUE), or {} when absent (fail-open).
    
    加载管理范围的 .env 文件（KEY=VALUE），如果不存在则返回 {}（失败打开）。

    解析结果会缓存并深拷贝返回。
    """
    managed_dir = get_managed_dir()
    if managed_dir is None:
        return {}
    parsed = _cached_read(managed_dir / ".env", _ENV_CACHE, _parse_env)
    return parsed if isinstance(parsed, dict) else {}


def apply_managed_overlay(config: dict) -> dict:
    """Overlay administrator-pinned config values on top of an already-built dict.

    The single, shared way for any config loader that builds its own dict
    (rather than going through hermes_cli.config.load_config) to honor managed
    scope. Mirrors hermes_cli.config._load_config_impl's managed merge exactly:

      * expand the managed config's ``${VAR}`` refs against the PROCESS env only
        (never user-config-defined refs), so a user cannot shadow a managed
        literal via a ${VAR} they control;
      * normalize the managed config's root ``model`` key (a bare ``model: x/y``
        string is promoted to ``model.default``) so it can't clobber the dict
        shape callers expect;
      * leaf-level deep-merge managed ON TOP, so managed wins per-leaf while
        sibling keys stay user-controlled.

    Fail-open: returns ``config`` unchanged if no managed scope is present or on
    any error — managed scope must never break a caller's startup. Mutates and
    returns ``config`` (callers pass a dict they own).

    将管理员固定的配置值覆盖到已构建的配置字典之上。

    这是任何配置加载器（不通过 hermes_cli.config.load_config 而是自己构建字典）用来
    遵循管理范围的唯一共享方式。该函数复制了 hermes_cli.config._load_config_impl 的管理合并逻辑：
      * 针对进程环境（仅 os.environ）展开管理配置中的 ${VAR} 引用，绝不使用用户定义的引用，
        以防用户通过自己控制的 ${VAR} 遮蔽管理字面值；
      * 归一化管理配置根部的 model 键（裸字符串 "model: x/y" 提升为 model.default），
        以免它用字符串覆盖调用方期望的字典形状；
      * 在叶子级别执行深度合并（managed 在上），确保 managed 在叶子键上获胜，
        而兄弟键仍然由用户控制。

    失败打开：如果没有管理范围或出现任何错误，则返回原 config 不变。
    管理范围绝不应破坏调用方的启动。本函数会修改并返回 config（调用方传入自己拥有的字典）。

    """
    try:
        managed = load_managed_config()
        if not managed:
            return config
        # Imported lazily to avoid an import cycle (config imports managed_scope).
        from strategy_cli.config import _deep_merge, _expand_env_vars, _normalize_root_model_keys

        managed_expanded = _normalize_root_model_keys(_expand_env_vars(managed))
        # A bare ``model: x/y`` string in the managed file must merge as
        # ``model.default`` — otherwise _deep_merge would replace the caller's
        # ``model`` dict with a string and break every ``cfg["model"]["..."]``
        # read. _normalize_root_model_keys only promotes the string when there
        # are root provider/base_url keys to migrate, so handle the bare case
        # here (matches cli.py's own string-model handling).

         # 管理文件中的裸 "model: x/y" 字符串必须合并为 model.default，
        # 否则 _deep_merge 会用字符串替换调用方的 model 字典，
        # 破坏所有 cfg["model"]["..."] 读取。
        # _normalize_root_model_keys 只有在存在 root provider/base_url 键要迁移时才提升字符串，
        # 因此这里额外处理裸字符串情况（与 cli.py 自己的字符串模型处理一致）。
        if isinstance(managed_expanded.get("model"), str):
            managed_expanded = dict(managed_expanded)
            managed_expanded["model"] = {"default": managed_expanded["model"]}
        return _deep_merge(config, managed_expanded)
    except Exception:  # noqa: BLE001 — overlay must never break a caller
        logger.warning("managed scope: failed to apply config overlay", exc_info=True)
        return config


def _parse_env(f) -> Dict[str, str]:
    """
    解析 .env 文件内容，返回键值对字典。

    忽略空行、注释行和不含 '=' 的行。去除键和值的首尾空白，并去除值两端的引号。
    """
    out: Dict[str, str] = {}
    for line in f:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        out[key.strip()] = value.strip().strip("\"'")
    return out


def _flatten_keys(d: dict, prefix: str = "") -> set:
    """
    将嵌套字典展开为点分隔的叶子键集合。

    例如：{"model": {"default": "gpt-4", "temperature": 0.7}} -> {"model.default", "model.temperature"}
    """
        
    keys: set = set()
    for k, v in d.items():
        dotted = f"{prefix}.{k}" if prefix else str(k)
        if isinstance(v, dict) and v:
            keys |= _flatten_keys(v, dotted)
        else:
            keys.add(dotted)
    return keys


def managed_config_keys() -> set:
    """Dotted leaf keys pinned by the managed config (e.g. {'model.default'}).
    
    返回管理配置中固定的点分隔叶子键集合（例如 {'model.default'}）。
    """
    return _flatten_keys(load_managed_config())


def is_key_managed(dotted_key: str) -> bool:
    """True if the exact dotted config key is pinned by the managed layer.
    
    判断指定的点分隔配置键是否由管理层固定（即用户不可覆盖）
    """
    return dotted_key in managed_config_keys()


def is_env_managed(name: str) -> bool:
    """True if the env var name is pinned by the managed .env layer.
    
    判断指定的环境变量名是否由管理 .env 层固定（即用户不可覆盖）。
    """
    return name in load_managed_env()
