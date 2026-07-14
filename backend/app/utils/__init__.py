# app/utils/__init__.py
from .data_utils import *
from .datetime_utils import *
from .task_utils import *
from .backtest_utils import *
# 自动导入模块方案，可以让utils下写的函数自动导入到utils包下，但是会导致vscode缺少函数提示，不太喜欢，暂时注释
# import importlib
# import pkgutil
# import inspect
# from pathlib import Path

# __all__ = []

# package_dir = Path(__file__).parent # 获取当前目录
# # 遍历当前目录下的所有模块
# for _, module_name, _ in pkgutil.iter_modules([str(package_dir)]):
#     # 跳过_开头的模块和 __init__.py
#     # python中_开头的函数或模块通常被视为私有的，不应该被外部直接使用，所以这里我们也跳过这些模块
#     if module_name.startswith('_') or module_name == '__init__':
#         continue
#     try:
#         # module表示导入的模块对象，例如 app.utils.data_utils
#         # import_module的第一个参数是模块名，第二个参数是包名（用于相对导入）
#         module = importlib.import_module(f'.{module_name}', package=__package__)
#         # 如果模块定义了 __all__，则只导出 __all__ 中的函数
#         if hasattr(module, '__all__'):
#             for name in module.__all__:
#                 obj = getattr(module, name, None)# 从子模块中获取该名字对应的对象，如果不存在则返回 None
#                 if inspect.isfunction(obj):
#                     # 将 obj 绑定到当前模块（即当前 __init__.py 所在的包）的全局命名空间，
#                     # 键名为 name，这样用户就可以直接使用包名.func_name 调用该函数。
#                     globals()[name] = obj
#                     # 同时将 name 添加到当前模块的 __all__ 列表（注意：原始代码中 __all__ 可能已经存在）。
#                     # 这样当 from package import * 时，这些函数也会被导出。
#                     __all__.append(name)
#         else:
#             # 否则导出所有非 _ 开头的函数
#             for name, obj in inspect.getmembers(module, inspect.isfunction):
#                 if not name.startswith('_'):
#                     globals()[name] = obj
#                     __all__.append(name)
#     except Exception as e:
#         import logging
#         logging.warning(f"无法导入工具模块 {module_name}: {e}")