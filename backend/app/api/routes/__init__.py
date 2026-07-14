# app/api/routes/__init__.py
import importlib
import pkgutil
from pathlib import Path

def register_routers(app):
    """
    自动遍历当前包下所有模块，注册其中名为 `router` 的 APIRouter 实例
    """
    package_dir = Path(__file__).parent
    for _, module_name, _ in pkgutil.iter_modules([str(package_dir)]):
        if module_name == '__init__':
            continue
        try:
            module = importlib.import_module(f'.{module_name}', package=__package__)
            if hasattr(module, 'router'):
                app.include_router(module.router)
        except Exception as e:
            # 如果某个模块导入失败，跳过并打印错误（可选）
            import logging
            logging.warning(f"无法加载路由模块 {module_name}: {e}")