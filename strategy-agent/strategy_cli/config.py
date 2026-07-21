import copy
import os
from pathlib import Path
import re
import shutil
import logging
import sys
import threading
import time
import traceback
from typing import Any, Dict, Optional, Tuple

import yaml

logger = logging.getLogger(__name__)

AGENT_ROOT = Path(__file__).resolve().parent.parent

_CONFIG_LOCK = threading.RLock()
# ---- 配置缓存 ----
# 键：配置文件路径（字符串）
# 值：元组 (文件修改时间_ns, 文件大小, 解析后的配置字典, 环境变量快照)
#
#   第1-2元素（int, int）: 文件的 mtime_ns 和 size，用于快速判断文件是否被修改。
#   第3元素（Dict[str, Any]）: 解析并展开环境变量后的完整配置数据（深拷贝）。
#   第4元素（Dict[str, Optional[str]]）: 配置中所有 ${VAR} 引用的环境变量值快照，
#       用于检测环境变量是否在缓存后被修改（例如延迟加载 .env 导致的环境变量变化），
#       若发生变化则缓存失效，强制重新加载。
_CACHE: Dict[str, Tuple[int, int, Dict[str, Any], Dict[str, Optional[str]]]] = {}
DEFAULT_CONFIG = {}

# 环境变量缓存（用于 load_env）
_env_cache: Optional[Tuple[Tuple, Dict[str, str]]] = None  # 添加这一行

# hermes中关于用户可交互配置的键值，暂时不用到
OPTIONAL_ENV_VARS = {
    # ── Provider (handled in provider selection, not shown in checklists) ──
    "NOUS_BASE_URL": {
        "description": "Nous Portal base URL override",
        "prompt": "Nous Portal base URL (leave empty for default)",
        "url": None,
        "password": False,
        "category": "provider",
        "advanced": True,
    }
}

# 环境变量中一些需要的配置，比如OPENAI_API_KEY
_EXTRA_ENV_KEYS = frozenset({
    "OPENAI_API_KEY",
})


_STRUCTURED_VALUE_MARKERS = ("://", "?", "&")

def get_home() -> Path:
    """
    原Hermes获取HERMES_HOME环境变量来得到项目路径，过于繁琐
    改为直接传递项目根目录
    """
    return AGENT_ROOT

def get_config_path() -> Path:
    """Get the main config file path."""
    return get_home() / "config.yaml"

def get_env_path() -> Path:
    """Get the .env file path (for API keys).
    路径agent/.env
    """
    return get_home() / ".env"



def _looks_like_structured_value(value: str) -> bool:
    """
    判断给定的字符串是否“看起来像”结构化数据（如 URL、查询字符串或包含空白符）。

    当返回 True 时，表示该值应被视为一个**不透明的整体**，即使其内部包含已知的
    `KEY=` 子串，也不应在此处拆分。这主要是为了防止将真正的值（如带查询参数的
    URL、带有路径的代理地址等）错误地当成多个环境变量条目。

    典型场景：
    - `value = "https://api.example.com?key=OPENAI_API_KEY=abc123"`
      → 虽然内部包含 `OPENAI_API_KEY=`，但它实际上是查询参数的一部分，
        不应被拆分为两行。
    - `value = "sk-12345678"`          → 不包含任何标记，视为普通 token
    - `value = "abc def"`              → 包含空格，视为结构化值（可能是含空格的配置）

    判断依据：
    1. 检查是否包含预定义的结构化标记
    2. 检查是否包含任何空白字符（空格、制表符等）
    """
    # 预定义的“结构化标记”集合，用于快速识别常见结构化格式。
    # 这些标记通常出现在 URL、查询字符串、路径、协议等中。
    # 具体内容由模块顶层的 _STRUCTURED_VALUE_MARKERS 定义，
    if any(marker in value for marker in _STRUCTURED_VALUE_MARKERS):
        return True
    # 如果值中包含任何空白字符（如空格、制表符、换行符），
    # 也视为结构化值（可能是包含空格的配置项，不应被拆分）。
    # 例如 "value with spaces" 很可能是一个完整配置项的一部分。
    return any(ch.isspace() for ch in value)

def _sanitize_env_lines(lines: list) -> list:
    """
    修复损坏的 .env 文件行，使其能被正确解析。

    主要处理两种损坏模式：
    1. 单行中连续拼接了多个 KEY=VALUE 对（缺少换行符），例如：
       ANTHROPIC_API_KEY=sk-...OPENAI_BASE_URL=https://...
       需要将其拆分为独立的两行。
    2. 残留的占位符条目（如 KEY=***），通常是配置未完成导致的无效值。

    设计原则：
    - 只根据“已知的环境变量键名”进行拆分，避免误伤值中恰好包含大写字母和“=”的正常文本。
    - 处理重叠匹配（例如 GLM_API_KEY= 包含 LM_API_KEY=），只保留最外层的匹配。
    - 只有当行首匹配到已知键，并且拆分后的每个“前导段”的值部分不像是结构化数据（如 URL/查询字符串）时，才执行拆分，否则保留原行。
    """
    # --- 1. 构建已知键名的集合（用于识别哪些 KEY= 是合法的拆分边界）---
    # OPTIONAL_ENV_VARS 是一个字典，其键为环境变量名；_EXTRA_ENV_KEYS 是一个 frozenset 集合。
    # 两者取并集，得到所有需要识别的键名。
    known_keys = set(OPTIONAL_ENV_VARS.keys()) | _EXTRA_ENV_KEYS

    sanitized: list[str] = []    # 存储处理后的每一行（末尾带换行符）
    for line in lines:
        raw = line.rstrip("\r\n")   # 移除行尾的换行符（保留原始缩进）
        stripped = raw.strip()      # 移除首尾空白，用于匹配和判断

        # 空行或注释行直接保留（不进行修复）
        if not stripped or stripped.startswith("#"):
            sanitized.append(raw + "\n")
            continue

        # --- 2. 查找该行中所有出现的已知键名（KEY=）的位置 ---
        # 例如，在 "ANTHROPIC_API_KEY=sk-...OPENAI_BASE_URL=https://..." 中，
        # 会同时匹配到 ANTHROPIC_API_KEY= 和 OPENAI_BASE_URL=，分别记录其起始和结束位置。
        match_ranges: list[tuple[int, int]] = []
        for key_name in known_keys:
            needle = key_name + "="
            idx = stripped.find(needle)
            while idx >= 0:
                match_ranges.append((idx, idx + len(needle)))   # 记录匹配的字符串在改行的起始位置和结束位置
                idx = stripped.find(needle, idx + len(needle))  # 继续查找下一个同名匹配

        # --- 3. 处理重叠匹配，只保留最外层（不被其他匹配完全包含的）匹配起始位置 ---
        # 例如，若同时匹配到 "GLM_API_KEY="（起始0）和 "LM_API_KEY="（起始1），
        # 后者被前者完全包含，因此只保留起始位置 0。
        split_positions = sorted({
            s for s, e in match_ranges
            if not any(
                s2 <= s and e2 >= e and (s2, e2) != (s, e)
                for s2, e2 in match_ranges
            )
        })  # split_positions记录的是所有可拆分字段的起始位置

        # --- 4. 判断是否应该拆分该行 ---
        # 条件：
        #   a) 存在至少两个匹配位置（即至少两个 KEY=）
        #   b) 第一个匹配必须位于行首（split_positions[0] == 0）
        #   c) 所有“前导段”的值部分（即每个 KEY= 后面的部分，直到下一个 KEY= 之前）
        #      都不像是结构化数据（如 URL、查询字符串等），以避免将 URL 中包含的 KEY= 错误拆分。
        split_into_entries = False
        segments: list[str] = []
        if len(split_positions) > 1 and split_positions[0] == 0:
            # 根据拆分位置切割原始行，得到若干段
            segments = [
                stripped[pos:(
                    split_positions[i + 1] if i + 1 < len(split_positions) else len(stripped)
                )]
                for i, pos in enumerate(split_positions)
            ]
            # 检查每个段（除了最后一个）的值部分是否非结构化
            # 例如 "sk-...OPENAI_BASE_URL=..." 中，段 "ANTHROPIC_API_KEY=sk-..." 的值部分为 "sk-..."
            # 而 "sk-..." 是简单 token，不是结构化值，因此允许拆分。
            # 但如果值是 "https://api.openai.com?key=OPENAI_API_KEY=xxx"，则值部分包含类似 URL 的结构，
            # 此时不应拆分，以免误伤。

            # 1、取出可拆分对象除最后一个外的所有segments = ["KEY1=value1", "KEY2=value2", "KEY3=value3"]
            #    仅取["KEY1=value1", "KEY2=value2"]，因为最后一个后面没有KEY=了无需判断是否结构化
            # 2、拆分出value部分的内容，判断是否结构化
            # 3、综上，判断segments[:-1] 中每一个段的值是否“非结构化”
            split_into_entries = all(
                not _looks_like_structured_value(seg.split("=", 1)[1])
                for seg in segments[:-1]
            )

        # --- 5. 执行拆分或保留原行 ---
        # 注意：此处的拆分是保守的拆分策略，只要该行数据出现了可能是结构化的数据就整行都不拆分
        if split_into_entries:
            for seg in segments:
                part = seg.strip()
                if part:
                    sanitized.append(part + "\n")
        else:
            # 不拆分，保留原始内容（但去除首尾空白，保持一致格式）
            sanitized.append(stripped + "\n")

    return sanitized

def _parse_env_value(raw_value: str) -> str:
    """
    解析 .env 文件中的值，处理引号、转义等，还原原始内容。

    支持三种格式：
    1. 无引号：直接返回去除首尾空白后的值
    2. 双引号："value" → 返回 value，并处理内部转义（\" 和 \\）
    3. 单引号：'value' → 返回 value，不处理任何转义（原样返回内部内容）

    注意：
        - 如果首尾都是双引号，则只处理双引号内部的转义字符（\" 和 \\），
          其他反斜杠保留原样。
        - 如果首尾都是单引号，则完全保留内部原始内容（不处理任何转义）。
    """
    # 去除首尾空白，但保留内部空格（等号右侧可能有空格）
    value = raw_value.strip()

    # ─── 情况1：双引号（支持内部转义）────────────────────────
    # 检查首尾是否都是双引号（且长度 >= 2）
    if len(value) >= 2 and value[0] == value[-1] == '"':
        quoted = value[1:-1]        # 去掉首尾的双引号
        parsed: list[str] = []      # 存储解析后的字符
        i = 0
        while i < len(quoted):
            ch = quoted[i]
            # 检查是否为反斜杠，且后面还有一个字符（可能是转义序列）
            if ch == "\\" and i + 1 < len(quoted):
                next_ch = quoted[i + 1]
                # 只处理 \" 和 \\ 两种转义
                if next_ch in {'"', "\\"}:
                    parsed.append(next_ch)
                    i += 2          # 跳过反斜杠和已转义的字符
                    continue
            # 普通字符或非识别的反斜杠，直接保留
            parsed.append(ch)
            i += 1
        return "".join(parsed)
    
    # ─── 情况2：单引号（不处理任何转义）────────────────────────
    # 检查首尾是否都是单引号（且长度 >= 2）
    if len(value) >= 2 and value[0] == value[-1] == "'":
        # 直接返回去掉首尾单引号的内容，内部原样保留（包括反斜杠）
        return value[1:-1]
    # ─── 情况3：无引号或引号不匹配 ─────────────────────────
    # 直接返回去除首尾空白的原始值
    return value

def load_env() -> Dict[str, str]:
    """
    从 .env 文件加载环境变量（路径由 get_env_path() 返回）。

    核心设计：
    1. **缓存机制**：基于文件修改时间（mtime）和大小，避免反复解析同一文件。
       - 因为 get_env_value() 在交互式界面中被频繁调用（数十到数百次），
         每次重新解析会消耗大量 CPU（~300ms），启用缓存后大幅提升性能。
       - 当用户编辑 .env 文件时，mtime 变化，缓存自动失效。
    2. **行清理**：先调用 _sanitize_env_lines() 修复常见损坏格式（如单行粘连多个 KEY=VALUE），
       再逐行解析。
    3. **容错编码**：强制使用 UTF-8 编码并容忍 BOM（Windows Notepad 会添加），
       避免因系统默认编码（如 cp1252）导致读取失败。
    4. **兼容 Bash 语法**：支持 `export KEY=value` 格式，自动去除 `export ` 前缀。

    返回值：
        Dict[str, str]：解析出的环境变量字典（键名 -> 值）。
        如果文件不存在或解析失败，返回空字典。

    注意：
        返回的是字典的副本（拷贝），确保外部修改不会影响内部缓存。
    """
    global _env_cache           # 声明使用模块级缓存变量
    env_path = get_env_path()   # 获取 .env 文件的路径（由其他函数提供）

    # --- 1. 构造缓存键（基于文件路径、修改时间和大小）---
    try:
        mtime = env_path.stat().st_mtime        # 文件最后修改时间
        size = env_path.stat().st_size          # 文件大小（字节）
        cache_key = (str(env_path), mtime, size)
    except FileNotFoundError:
        # 文件不存在时，用 None 标记，但不影响后续处理
        cache_key = (str(env_path), None, None)
    except Exception:
        # 其他异常（如权限问题）则放弃缓存
        cache_key = None

    # --- 2. 检查缓存是否命中 ---
    if cache_key is not None and _env_cache is not None:
        cached_key, cached_vars = _env_cache
        if cached_key == cache_key:
            # 命中缓存，直接返回拷贝（防止外部修改影响缓存）
            return dict(cached_vars)

    # --- 3. 未命中缓存，执行实际加载 ---
    env_vars: Dict[str, str] = {}

    if env_path.exists():
        # 3.1 读取文件（指定 UTF-8 编码，容忍 BOM）
        # Windows 下 open() 默认用系统编码（如 cp1252），可能无法解析 UTF-8 的 .env，
        # 显式指定 utf-8-sig 可自动跳过 BOM 并正确解码。
        open_kw = {"encoding": "utf-8-sig", "errors": "replace"}
        with open(env_path, **open_kw) as f:
            raw_lines = f.readlines()
        # 3.2 清理损坏的行（拆分粘连行、移除无效占位符等）
        lines = _sanitize_env_lines(raw_lines)

        # 3.3 逐行解析
        for line in lines:
            line = line.strip()
            # 忽略空行和注释行，只处理包含 '=' 的行
            if line and not line.startswith('#') and '=' in line:
                # 兼容 bash 风格的 `export KEY=value`，去掉 `export `
                if line.startswith('export '):
                    line = line[7:]
                # 按第一个 '=' 切分，得到 key 和 value
                key, _, value = line.partition('=')
                # 去除键名首尾空格，解析值（处理引号、转义等）
                env_vars[key.strip()] = _parse_env_value(value)

    # ─── 4. 更新缓存（如果缓存键有效）─────────────────────────
    if cache_key is not None:
        _env_cache = (cache_key, dict(env_vars))

    return env_vars


def get_env_value(key: str) -> Optional[str]:
    """Get a value from .env or environment."""
    # Check environment first
    if key in os.environ:
        return os.environ[key]

    # Then check .env file
    env_vars = load_env()
    return env_vars.get(key)



def load_config() -> Dict[str, Any]:
    """Load configuration from ~/.hermes/config.yaml.

    Cached on the config file's (mtime_ns, size). Returns a deepcopy of
    the cached value when unchanged, since most call sites mutate the
    result (e.g. ``cfg["model"]["default"] = ...`` before ``save_config``).
    The cache is keyed on ``str(config_path)`` so profile switches
    (which change ``HERMES_HOME`` and therefore ``get_config_path()``)
    don't collide.

    Read-only callers should use ``load_config_readonly()`` to skip the
    defensive deepcopy — that path matters in agent-loop hot spots like
    ``get_provider_request_timeout`` which is called once per API turn.

    从 ~/.hermes/config.yaml 加载配置（实际路径由 get_config_path() 决定）。

    设计要点：
        1. 基于文件修改时间（mtime_ns）和大小进行缓存，避免重复读取和解析 YAML。
        2. 返回的是**深拷贝**（deepcopy）的缓存值，因为大多数调用方会修改返回的字典
           （例如 cfg["model"]["default"] = "gpt-4" 后再调用 save_config），
           如果直接返回缓存的内部字典，修改会污染缓存，导致后续读取得到意外结果。
        3. 缓存键包含配置文件的完整路径，以支持通过 HERMES_HOME 切换配置文件目录，
           防止不同环境的配置互相干扰。
        4. 只读场景（如频繁调用的 get_provider_request_timeout）应使用
           load_config_readonly() 跳过深拷贝，提升性能。

    返回:
        Dict[str, Any]: 配置字典（深拷贝版本）。
    """
    return _load_config_impl(want_deepcopy=True)

def load_config_readonly() -> Dict[str, Any]:
    """Fast-path variant of ``load_config()`` for callers that ONLY READ.

    Returns the cached config dict directly without the defensive deepcopy
    that ``load_config()`` applies. **Mutating the returned dict (or any
    nested structure) corrupts the in-process cache for every subsequent
    caller** — only use this when you are absolutely sure your code path
    will not write to the result. If you need to mutate or pass to
    ``save_config``, call ``load_config()`` instead.

    Why this exists: ``load_config()`` cache-hit cost is ~265us per call,
    half of which (~135us) is the defensive deepcopy. The agent loop calls
    into config reads (timeouts, thresholds, feature flags) ~20-50x per
    conversation; skipping deepcopy here removes a measurable allocation
    source and the GC pressure that comes with it.

    Note: this returns a plain ``dict`` (not ``MappingProxyType``) so
    existing ``isinstance(x, dict)`` guards downstream keep working. The
    safety guarantee is purely documented, not enforced — be careful.

    从 config.yaml 加载配置（实际路径由 get_config_path() 决定）。

    设计要点：
        1. 基于文件修改时间（mtime_ns）和大小进行缓存，避免重复读取和解析 YAML。
        2. 返回的是**深拷贝**（deepcopy）的缓存值，因为大多数调用方会修改返回的字典
           （例如 cfg["model"]["default"] = "gpt-4" 后再调用 save_config），
           如果直接返回缓存的内部字典，修改会污染缓存，导致后续读取得到意外结果。
        3. 缓存键包含配置文件的完整路径，以支持通过 HERMES_HOME 切换配置文件目录，
           防止不同环境的配置互相干扰。
        4. 只读场景（如频繁调用的 get_provider_request_timeout）应使用
           load_config_readonly() 跳过深拷贝，提升性能。

    返回:
        Dict[str, Any]: 配置字典（深拷贝版本）。
    """
    return _load_config_impl(want_deepcopy=False)


def _load_config_impl(*, want_deepcopy: bool) -> Dict[str, Any]:
    """
    加载配置文件的内部实现，支持缓存、环境变量展开，并可选择深拷贝。

    参数：
        want_deepcopy: True 返回深拷贝（允许调用方修改）；False 返回缓存引用（只读，性能更高）。

    返回：
        配置字典（环境变量已展开）。
    """
    # ---- 线程锁保护 ----
    # 使用可重入锁（RLock）保护整个加载过程，因为 save_config 内部会调用本函数，
    # 且多个线程可能同时读写配置。此外，libyaml 的 C 扩展非线程安全。
    with _CONFIG_LOCK:
        config_path = get_config_path()
        path_key = str(config_path)

        # ---- 计算缓存签名（修改时间 + 文件大小） ----
        try:
            st = config_path.stat()
            user_sig = (st.st_mtime_ns, st.st_size)
        except FileNotFoundError:
            user_sig = None

        # ---- 检查缓存 ----
        cached = _CACHE.get(path_key)
        if cached is not None and user_sig is not None and cached[:2] == user_sig:
            # 检查环境变量是否与缓存时一致
            env_snapshot = cached[3]
            if all(os.environ.get(k) == v for k, v in env_snapshot.items()):
                return copy.deepcopy(cached[2]) if want_deepcopy else cached[2]

        # ---- 加载配置 ----
        config = copy.deepcopy(DEFAULT_CONFIG)

        if user_sig is not None:
            try:
                with open(config_path, encoding="utf-8") as f:
                    user_config = yaml.safe_load(f) or {}
                # 深度合并用户配置到默认配置之上
                config = _deep_merge(config, user_config)
            except Exception as e:
                # 解析失败，可以记录日志或直接使用默认配置（这里保留错误反馈）
                # 此处简单返回默认配置（也可选择抛出）
                logger.warning(f"[ERROR] Failed to parse config.yaml: {e}")
                logger.debug(traceback.format_exc())  # 打印详细堆栈到 debug 日志
                

        # ---- 展开环境变量 ----
        expanded = _expand_env_vars(config)

        # ---- 更新缓存 ----
        if user_sig is not None:
            env_snapshot = _env_ref_snapshot(expanded)
            cached_copy = copy.deepcopy(expanded)
            _CACHE[path_key] = (user_sig[0], user_sig[1], cached_copy, env_snapshot)
            if not want_deepcopy:
                return cached_copy
        else:
            _CACHE.pop(path_key, None)
            
        return expanded
    
def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge *override* into *base*, preserving nested defaults.

    Keys in *override* take precedence. If both values are dicts the merge
    recurses, so a user who overrides only ``tts.elevenlabs.voice_id`` will
    keep the default ``tts.elevenlabs.model_id`` intact.

    An empty section key in config.yaml (``terminal:`` with no value) parses
    as YAML ``None``; treating that as an override would replace the entire
    default dict with ``None`` and crash every downstream consumer that
    expects a mapping (#58277). A ``None`` override of a dict default is
    ignored — same as the key being absent.

    递归地将 override 字典合并到 base 字典中，保留 base 中的嵌套默认值。

    合并规则：
        - override 中的键优先级更高，即如果键在两者中都存在，采用 override 的值。
        - 如果值都是字典，则递归合并（深层合并）。
        - 如果 base 中的值是字典，而 override 中的值显式为 None，则跳过该键，
          不覆盖原有的字典（避免用 None 替换整个字典导致后续代码崩溃）。

    典型使用场景：
        将用户配置（override）覆盖到默认配置（base）之上，用户只需指定需要修改的部分，
        未指定的键仍保留默认值。

    参数:
        base: 基础字典（通常是默认配置）。
        override: 覆盖字典（通常是用户配置）。

    返回:
        合并后的新字典（不修改原始 base）。
    """
    # 复制一份基础字典，避免修改原始数据
    result = base.copy()
    for key, value in override.items():
        # 如果当前键在 result 中存在，且两个值都是字典，则递归合并
        if (
            key in result
            and isinstance(result[key], dict)
            and isinstance(value, dict)
        ):
            result[key] = _deep_merge(result[key], value)
        # 特殊处理：如果 base 中该键是字典，但 override 中值为 None，
        # 则忽略（不覆盖），防止用 None 替换整个字典。
        elif key in result and isinstance(result[key], dict) and value is None:
            continue
        # 其他情况：直接覆盖（包括普通值、列表等）
        else:
            result[key] = value
    return result

def _expand_env_vars(obj):
    """Recursively expand ``${VAR}`` references in config values.

    Only string values are processed; dict keys, numbers, booleans, and
    None are left untouched.  Unresolved references (variable not in
    ``os.environ``) are kept verbatim so callers can detect them.

    递归地展开配置值中的 ${VAR} 环境变量引用。

    处理规则：
        - 仅处理字符串类型（str）的值，查找其中的 ${VAR} 模式并替换为 os.environ 中对应的环境变量值。
        - 如果环境变量不存在，则保留原始 ${VAR} 不变（即不替换）。
        - 字典的键、数字、布尔值、None 等类型不受影响。
        - 嵌套结构（如列表、字典）会递归处理所有子元素。

    参数:
        obj: 要处理的任意值（字符串、字典、列表、数字等）。

    返回:
        处理后的值（可能是新字符串或原对象）。
    """
    if isinstance(obj, str):
        # 使用正则替换所有 ${VAR} 模式
        return re.sub(
            r"\${([^}]+)}",
            lambda m: os.environ.get(m.group(1), m.group(0)),# 存在则替换，否则保留原样
            obj,
        )
    if isinstance(obj, dict):
        # 递归处理字典的每个值
        return {k: _expand_env_vars(v) for k, v in obj.items()}
    if isinstance(obj, list):
        # 递归处理列表的每个元素
        return [_expand_env_vars(item) for item in obj]
    # 其他类型（数字、布尔、None 等）原样返回
    return obj


def _env_ref_snapshot(obj, snapshot=None):
    """Map every ``${VAR}`` name referenced in config values to its current
    ``os.environ`` value (``None`` when unset).

    Stored alongside cached ``load_config()`` results so a cache hit can
    detect that the cached expansion was made against a *different*
    environment — e.g. a ``load_config()`` that ran before
    ``load_hermes_dotenv()`` populated the process env, or an env var
    rotated in-process after the first load. File mtime/size alone cannot
    see either case (#58514).

    递归遍历配置对象，收集所有 ${VAR} 环境变量引用，并记录它们当前的值（快照）。

    这个函数用于缓存失效检测：当配置加载并展开环境变量后，如果之后环境变量发生了变化
    （例如 .env 文件延迟加载或进程内环境变量旋转），仅凭文件修改时间无法感知这种变化。
    通过保存配置中引用的所有环境变量的值快照，缓存命中时可以检查当前环境是否与快照一致，
    若不一致则强制重新加载配置，避免使用过期的展开值。

    参数:
        obj: 要扫描的对象，可以是字符串、字典、列表或任何其他类型（非字符串/字典/列表则忽略）。
        snapshot: 可选，用于累积结果的字典（递归调用时传递）。若不提供，则自动创建。

    返回:
        Dict[str, Optional[str]]: 键为环境变量名（如 "API_KEY"），值为该变量在调用时
        os.environ.get(name) 的结果（若未设置则为 None）。
    """
    # 如果 snapshot 未传入，初始化空字典
    if snapshot is None:
        snapshot = {}

    # 如果是字符串，使用正则查找所有 ${VAR} 模式，提取变量名并记录其当前值
    if isinstance(obj, str):
        for name in re.findall(r"\${([^}]+)}", obj):
            snapshot[name] = os.environ.get(name)
    # 如果是字典，递归处理每个值
    elif isinstance(obj, dict):
        for value in obj.values():
            _env_ref_snapshot(value, snapshot)
     # 如果是列表，递归处理每个元素
    elif isinstance(obj, list):
        for item in obj:
            _env_ref_snapshot(item, snapshot)
    # 其他类型（数字、布尔、None 等）忽略，因为它们不包含环境变量引用
    return snapshot


# ============================================================================
# 原始配置缓存（Raw Config Cache）
# ============================================================================
# 与 _LOAD_CONFIG_CACHE 模式相同，但用于 read_raw_config()。
# 当调用方需要获取用户磁盘上的原始值（未合并默认值）时使用。
# 键：文件路径
# 值：(修改时间_ns, 文件大小, 解析后的原始字典)
_RAW_CONFIG_CACHE: Dict[str, Tuple[int, int, Dict[str, Any]]] = {}

# ============================================================================
# 快速 YAML 加载（使用 libyaml C 扩展加速）
# ============================================================================
# PyYAML 的纯 Python SafeLoader 比 libyaml 支持的 CSafeLoader C 扩展慢约 8 倍。
# 启动时解析 config.yaml 和每个插件清单都使用慢速路径，花费约 0.9 秒冷启动时间。
# C 加载器是 safe_load 的真正替换（相同的受限标签集），因此优先使用它，
# 仅当 libyaml 未编译时回退到纯 Python 加载器。
_fast_yaml_loader = None

def _get_fast_yaml_loader():
    global _fast_yaml_loader
    if _fast_yaml_loader is None:
        # 尝试使用 CSafeLoader（libyaml C 扩展），否则回退到 SafeLoader
        _fast_yaml_loader = getattr(yaml, "CSafeLoader", None) or yaml.SafeLoader
    return _fast_yaml_loader


def fast_safe_load(stream: Any) -> Any:
    """使用 libyaml C 加载器（如果可用）进行 yaml.safe_load。

    接受与 yaml.safe_load 相同的输入（字符串/字节文档或可读文件对象），
    返回相同的解析结构。当 CSafeLoader 不可用时回退到纯 Python SafeLoader，
    因此行为在任何地方都相同——只是速度不同。
    """
    return yaml.load(stream, Loader=_get_fast_yaml_loader())

# ============================================================================
# 配置解析失败警告（防止重复输出）
# ============================================================================
# 跟踪哪些 (config_path, mtime_ns, size) 元组我们已经警告过，
# 以免并发的 CLI/gateway 加载损坏的 config.yaml 时反复向 stderr 输出。
# 当文件更改（不同 mtime）时自动清除。
_CONFIG_PARSE_WARNED: set = set()

def _backup_corrupt_config(config_path: Path) -> Optional[Path]:
    """将损坏的 config.yaml 复制到带时间戳的 .bak 备份文件。

    当 YAML 无法解析时，load_config() 静默回退到 DEFAULT_CONFIG，
    而用户损坏的文件仍留在磁盘上。该文件是用户预期覆盖内容的唯一副本——
    如果他们重新运行设置向导或 hermes config set（会重写 config.yaml），
    损坏但可恢复的内容将永久丢失。

    此函数将损坏的文件快照到 config.yaml.corrupt.<ts>.bak，
    以便用户可以 diff/修复它。与 Gemini CLI 的策略文件恢复（将活动文件重置为干净状态）
    不同，我们故意保留 config.yaml：hermes 从不静默修改用户的配置，
    保留它意味着手动修复的文件将在下次加载时被重新读取。
    备份是尽力而为的——任何失败（权限、符号链接、磁盘满）都会被吞掉，
    以免配置加载被备份问题阻塞。

    返回备份路径（成功时）或 None。不跟踪/复制符号链接（镜像 Gemini #21541 的 lstat 防护），
    以避免覆盖恶意/错误配置的符号链接所指向的内容。
    """
    try:
        if config_path.is_symlink():
            return None
        st = config_path.stat()
        if st.st_size == 0:
            # 空文件不值得保留，而且 yaml.safe_load 会返回 {}（所以不会到达这里），
            # 但以防万一进行防护。
            return None
        ts = time.strftime("%Y%m%d-%H%M%S")
        backup_path = config_path.with_name(f"{config_path.name}.corrupt.{ts}.bak")
        # 不覆盖同一秒内已存在的备份；如果已有同 mtime 的损坏备份，
        # 假定此损坏已被快照，跳过（去重缓存通常阻止第二次调用，但进程重启会清除它）。
        sibling_baks = list(
            config_path.parent.glob(f"{config_path.name}.corrupt.*.bak")
        )
        for existing in sibling_baks:
            try:
                if existing.stat().st_size == st.st_size:
                    # 与当前损坏文件大小相同——很可能是相同的损坏已保存，避免备份轮换。
                    return None
            except OSError:
                continue
        if backup_path.exists():
            return None
        shutil.copy2(config_path, backup_path)
        return backup_path
    except Exception:
        return None
    
def _warn_config_parse_failure(
    config_path: Path, exc: Exception, *, fallback: str = "defaults"
) -> None:
    """
    向用户、日志和 stderr 输出 config.yaml 解析失败信息。

    ~/.hermes/config.yaml 的 YAML 解析错误会导致 load_config() 静默回退到 DEFAULT_CONFIG，
    这意味着每个用户覆盖（辅助提供者、回退链、模型覆盖等）都被丢弃。
    在引入此帮助函数之前，只是单行 print(...) 在首次调用时滚出屏幕，再也看不到。

    现在：对每个 (path, mtime_ns, size) 在 stderr **和** agent.log / errors.log
    中以 WARNING 级别警告一次，因此 hermes logs 会显示它。
    如果文件更改（不同 mtime/size）会自动重新警告，因此用户编辑配置文件时会看到下一次失败。
    对于给定损坏文件的第一次警告，我们还会将其快照到带时间戳的 .bak（尽力而为），
    以便用户的恢复内容在之后设置向导或 hermes config set 重写 config.yaml 时得以保留。

    fallback 选择措辞："defaults"（新进程，没有其他可服务的）或 "last-known-good"
    （进程内保留先前加载的配置——参见 _load_config_impl 中的 codex#31188 移植）。
    """
    try:
        st = config_path.stat()
        key = (str(config_path), st.st_mtime_ns, st.st_size)
    except OSError:
        key = (str(config_path), 0, 0)
    if key in _CONFIG_PARSE_WARNED:
        return
    _CONFIG_PARSE_WARNED.add(key)

    backup_path = _backup_corrupt_config(config_path)

    if fallback == "last-known-good":
        msg = (
            f"Failed to parse {config_path}: {exc}. "
            f"Keeping the previously loaded config for this process — "
            f"edits to config.yaml are being IGNORED until the YAML is fixed."
        )
    else:
        msg = (
            f"Failed to parse {config_path}: {exc}. "
            f"Falling back to default config — every user override "
            f"(auxiliary providers, fallback chain, model settings) is being IGNORED. "
            f"Fix the YAML and restart."
        )
    if backup_path is not None:
        msg += f" A copy of the corrupted file was saved to {backup_path}."
    logger.warning(msg)
    try:
        sys.stderr.write(f"⚠️  hermes config: {msg}\n")
        sys.stderr.flush()
    except Exception:
        pass

# ============================================================================
# 原始配置读取（read_raw_config）
# ============================================================================
def read_raw_config() -> Dict[str, Any]:
    """
    按原样读取 ~/.hermes/config.yaml，不合并默认值或执行迁移。

    返回原始 YAML 字典，如果文件不存在或无法解析则返回 {}。
    用于轻量级配置读取，只需单个值且不想承担 load_config() 的深度合并+迁移管道开销。

    基于文件 (mtime_ns, size) 进行缓存——与 load_config() 策略相同。
    每次调用返回深拷贝，因为某些调用方在传递给 save_config() 之前会修改结果。
    """
    with _CONFIG_LOCK:
        try:
            config_path = get_config_path()
            st = config_path.stat()
            cache_key = (st.st_mtime_ns, st.st_size)
        except (FileNotFoundError, OSError):
            return {}

        path_key = str(config_path)
        cached = _RAW_CONFIG_CACHE.get(path_key)
        if cached is not None and cached[:2] == cache_key:
            return copy.deepcopy(cached[2])

        try:
            with open(config_path, encoding="utf-8") as f:
                data = fast_safe_load(f) or {}
        except Exception as e:
            _warn_config_parse_failure(config_path, e)
            return {}

        if not isinstance(data, dict):
            data = {}
        _RAW_CONFIG_CACHE[path_key] = (cache_key[0], cache_key[1], copy.deepcopy(data))
        return data