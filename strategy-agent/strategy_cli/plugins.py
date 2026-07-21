# agent/plugin_loader.py
"""
轻量级插件加载器，用于自动发现 plugins/web/ 下的 Web 搜索后端。

这是 Hermes 插件系统的简化版本，只保留了：
- 扫描指定目录下的子文件夹，查找 plugin.yaml
- 解析 YAML 获取插件元数据
- 动态导入 __init__.py 并执行 register(ctx)
- 通过 PluginContext 将 WebSearchProvider 注册到 web_search_registry

不包含：hooks、middleware、CLI 命令、平台适配、工具注册等高级功能。
"""

from __future__ import annotations

import importlib.util
import logging
import sys
import types
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ===========================================================================
# 数据类
# ===========================================================================

@dataclass
class PluginManifest:
    """
    plugin.yaml 的解析结果，包含插件的元数据。

    字段说明：
        name: 插件名称（如 "ddgs"）
        version: 版本号（可选）
        description: 简短描述（可选）
        author: 作者（可选）
        kind: 插件类型，对于 Web 搜索后端为 "backend"
        key: 唯一标识，通常与 name 相同，但可以用于分类命名空间（如 "web/ddgs"）
        path: 插件目录的绝对路径，用于后续加载 __init__.py
    """
    name: str
    version: str = ""
    description: str = ""
    author: str = ""
    kind: str = "backend"          # 只关心 backend
    key: str = ""                  # 插件唯一标识
    path: Optional[str] = None     # 插件目录路径


@dataclass
class LoadedPlugin:
    """
    运行时已加载的插件状态。

    字段说明：
        manifest: 插件的元数据
        module: 导入后的模块对象（即 __init__.py 对应的模块）
        enabled: 是否成功启用（注册过程无异常）
        error: 若加载失败，记录错误信息
    """
    manifest: PluginManifest
    module: Optional[types.ModuleType] = None
    enabled: bool = False
    error: Optional[str] = None


# ===========================================================================
# 插件上下文 (只保留 Web 搜索注册)
# ===========================================================================

class PluginContext:
    """
    提供给插件的上下文对象，插件的 register(ctx) 函数会接收此实例。

    这是插件与主系统交互的“桥梁”。插件通过调用 ctx 上的注册方法，
    将其功能注入到系统中。此处只保留 Web 搜索提供者的注册方法，
    其他 Hermes 中的注册方法（工具、钩子、命令等）均被移除。

    设计原则：只暴露必要的方法，降低插件对系统内部的依赖。
    """
    def __init__(self, manifest: PluginManifest, manager: "PluginManager"):
        self.manifest = manifest
        self._manager = manager

    def register_web_search_provider(self, provider) -> None:
        """
        注册 Web 搜索提供者（由 plugins/web/ddgs/provider.py 中的 register 函数调用）。

        参数：
            provider: 必须继承自 WebSearchProvider 的实例（如 DDGSWebSearchProvider）

        流程：
            1. 延迟导入 web_search_provider 和 web_search_registry 避免循环依赖
            2. 类型检查，确保 provider 是正确的类型
            3. 调用 web_search_registry.register_provider() 将 provider 存入全局注册表
            4. 记录日志
        """
        # 延迟导入以避免模块循环依赖（plugin_loader -> web_search_provider -> ...）
        from agent.web_search_provider import WebSearchProvider
        from agent.web_search_registry import register_provider as _register_web_provider

        # 类型安全：如果不是 WebSearchProvider 的子类，忽略并警告
        if not isinstance(provider, WebSearchProvider):
            logger.warning(
                f"Plugin '{self.manifest.name}' tried to register a web provider "
                "that does not inherit from WebSearchProvider. Ignoring."
            )
            return
        # 执行注册
        _register_web_provider(provider)
        logger.info(f"Plugin '{self.manifest.name}' registered web provider: {provider.name}")


# ===========================================================================
# 插件管理器 (精简版)
# ===========================================================================

class PluginManager:
    """
    插件管理器，负责扫描、解析、加载插件。

    流程：
        1. discover_and_load() 扫描指定目录（plugins/web/）
        2. _scan_directory() 遍历子目录，查找 plugin.yaml
        3. _parse_manifest() 解析 YAML 生成 PluginManifest
        4. 对每个 manifest 调用 _load_plugin()
        5. _load_plugin() 动态导入 __init__.py，获取 register 函数
        6. 创建 PluginContext，调用 register(ctx)
        7. register 内部会调用 ctx.register_web_search_provider() 完成注册
    """
    def __init__(self):
        # 存储已加载的插件，键为 manifest.key 或 manifest.name
        self._plugins: Dict[str, LoadedPlugin] = {}
        # 防止重复扫描
        self._discovered: bool = False

    def discover_and_load(self, force: bool = False) -> None:
        """
        扫描并加载插件，仅搜索 plugins/web/ 目录。

        参数：
            force: 若为 True，清除已加载状态并重新扫描（主要用于测试或热加载）
        """
        if self._discovered and not force:
            return
        if force:
            self._plugins.clear()
        self._discovered = True
        try:
            self._discover_and_load_inner()
        except BaseException:
            # 如果扫描过程中发生异常，重置标志以便下次重试
            self._discovered = False
            raise

    def _discover_and_load_inner(self) -> None:
        """
        实际的扫描与加载逻辑。

        获取项目根目录下的 plugins/web/ 目录，调用 _scan_directory 收集所有 manifest，
        然后逐个加载。
        """
        # 从 config.py 获取项目根目录（由 get_home() 决定，默认为当前目录）
        from strategy_cli.config import get_home
        base_dir = get_home() / "plugins" / "web"
        if not base_dir.is_dir():
            logger.debug(f"Web plugins directory not found: {base_dir}")
            return

        manifests = self._scan_directory(base_dir, source="project")
        # 按 key 去重（如果同一个 key 出现多次，只保留最后一个）
        winners: Dict[str, PluginManifest] = {}
        for m in manifests:
            winners[m.key or m.name] = m

        for manifest in winners.values():
            self._load_plugin(manifest)

        if manifests:
            logger.info(f"Plugin discovery complete: found {len(manifests)} plugin(s)")

    def _scan_directory(self, path: Path, source: str) -> List[PluginManifest]:
        """
        扫描 path 下的子目录，查找 plugin.yaml（也支持 .yml 扩展名）。

        参数：
            path: 要扫描的目录（如 plugins/web/）
            source: 来源标识（仅用于日志，此处固定为 "project"）

        返回：
            PluginManifest 列表
        """
        manifests = []
        if not path.is_dir():
            return manifests
        for child in sorted(path.iterdir()):
            if not child.is_dir():
                continue
            manifest_file = child / "plugin.yaml"
            if not manifest_file.exists():
                manifest_file = child / "plugin.yml"
            if manifest_file.exists():
                m = self._parse_manifest(manifest_file, child, source)
                if m:
                    manifests.append(m)
        return manifests

    def _parse_manifest(self, manifest_file: Path, plugin_dir: Path, source: str) -> Optional[PluginManifest]:
        """
        解析单个 plugin.yaml 文件，返回 PluginManifest 对象。

        参数：
            manifest_file: plugin.yaml 的路径
            plugin_dir: 插件所在目录
            source: 来源标识

        返回：
            成功返回 PluginManifest，失败返回 None（并记录警告）
        """
        try:
            import yaml
            data = yaml.safe_load(manifest_file.read_text(encoding="utf-8")) or {}
            name = data.get("name", plugin_dir.name)
            key = data.get("key", name)
            kind = data.get("kind", "standalone")
            return PluginManifest(
                name=name,
                version=str(data.get("version", "")),
                description=data.get("description", ""),
                author=data.get("author", ""),
                kind=kind,
                key=key,
                path=str(plugin_dir),
            )
        except Exception as e:
            logger.warning(f"Failed to parse {manifest_file}: {e}")
            return None

    def _load_plugin(self, manifest: PluginManifest) -> None:
        """
        加载一个具体的插件：导入模块，调用 register 函数。

        流程：
            1. 创建 LoadedPlugin 实例
            2. 调用 _load_directory_module() 动态导入 __init__.py
            3. 检查是否有 register 函数
            4. 如果有，创建 PluginContext，调用 register(ctx)
            5. 标记加载成功或记录错误
            6. 存入 _plugins 字典
        """
        loaded = LoadedPlugin(manifest=manifest)
        try:
            module = self._load_directory_module(manifest)
            loaded.module = module
            register_fn = getattr(module, "register", None) # 查找插件的register方法
            if register_fn is None:
                loaded.error = "no register() function"
                logger.warning(f"Plugin {manifest.name} has no register() function")
            else:
                ctx = PluginContext(manifest, self)
                register_fn(ctx)   # 插件在此处调用 ctx.register_web_search_provider()
                loaded.enabled = True
                logger.debug(f"Plugin {manifest.name} loaded successfully")
        except Exception as e:
            loaded.error = str(e)
            logger.warning(f"Failed to load plugin {manifest.name}: {e}")
        self._plugins[manifest.key or manifest.name] = loaded

    def _load_directory_module(self, manifest: PluginManifest) -> types.ModuleType:
        """
        动态导入插件目录下的 __init__.py 文件。

        参数：
            manifest: 插件元数据，其中包含 path 字段

        返回：
            导入后的模块对象

        实现细节：
            - 使用 importlib.util.spec_from_file_location 创建模块规范
            - 使用唯一的模块名（基于 key）避免与系统模块冲突
            - 将模块添加到 sys.modules 中，便于后续引用
        """
        plugin_dir = Path(manifest.path)
        init_file = plugin_dir / "__init__.py"
        if not init_file.exists():
            raise FileNotFoundError(f"No __init__.py in {plugin_dir}")

        # 生成唯一的模块名，例如 _web_plugin_ddgs 或 _web_plugin_web_ddgs（如果 key 包含路径）
        module_name = f"_web_plugin_{manifest.key.replace('/', '__').replace('-', '_')}"
        spec = importlib.util.spec_from_file_location(module_name, init_file)
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot create module spec for {init_file}")
        module = importlib.util.module_from_spec(spec)
        # 将模块添加到 sys.modules 以便缓存，防止重复导入
        sys.modules[module_name] = module
        # 执行模块代码（即运行 __init__.py）
        spec.loader.exec_module(module)
        return module


# ===========================================================================
# 全局单例与便利函数
# ===========================================================================

_manager: Optional[PluginManager] = None


def get_plugin_manager() -> PluginManager:
    """
    获取全局唯一的 PluginManager 实例（单例模式）。

    如果尚未创建，则创建一个新实例并返回。
    """
    global _manager
    if _manager is None:
        _manager = PluginManager()
    return _manager


def discover_web_plugins(force: bool = False) -> None:
    """
    对外暴露的入口：加载所有 Web 搜索插件。

    调用此函数后，所有位于 plugins/web/ 下的插件会被自动扫描并注册。

    参数：
        force: 若为 True，强制重新扫描并重新加载所有插件
    """
    get_plugin_manager().discover_and_load(force=force)