"""
工具包初始化
"""
from tools.registry import registry, tool

# 导入所有工具以触发注册
from tools import terminal
from tools import file_ops
from tools import search
from tools import batch_edit
from tools import git_ops
from tools import sub_agent
from tools import browser
from tools import web

# 导入记忆工具（在 memory 包中，但也通过工具注册系统管理）
import memory.tools  # noqa: F401 — 触发 @tool 装饰器注册

__all__ = ["registry", "tool"]
