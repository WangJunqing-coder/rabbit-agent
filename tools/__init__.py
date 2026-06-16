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

__all__ = ["registry", "tool"]
