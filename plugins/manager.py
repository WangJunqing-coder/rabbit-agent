"""
插件/技能系统
"""
import os
import json
import logging
import importlib.util
from pathlib import Path
from typing import Optional, Callable
from dataclasses import dataclass, field

from tools.registry import registry

logger = logging.getLogger("rabbit_agent.plugins")


@dataclass
class Plugin:
    """插件定义"""
    name: str
    description: str
    version: str
    author: str
    tools: list[str] = field(default_factory=list)
    enabled: bool = True


class PluginManager:
    """插件管理器"""
    
    def __init__(self, plugins_dir: str = None):
        self.plugins_dir = plugins_dir or os.path.join(
            os.path.expanduser("~"), ".liteagent", "plugins"
        )
        os.makedirs(self.plugins_dir, exist_ok=True)
        self.plugins: dict[str, Plugin] = {}
    
    def discover_plugins(self) -> list[Plugin]:
        """发现可用插件"""
        plugins = []
        
        for item in Path(self.plugins_dir).iterdir():
            if item.is_dir():
                manifest_path = item / "manifest.json"
                if manifest_path.exists():
                    try:
                        with open(manifest_path, "r") as f:
                            manifest = json.load(f)
                        
                        plugin = Plugin(
                            name=manifest.get("name", item.name),
                            description=manifest.get("description", ""),
                            version=manifest.get("version", "1.0.0"),
                            author=manifest.get("author", "Unknown")
                        )
                        plugins.append(plugin)
                    except Exception:
                        continue
        
        return plugins
    
    def load_plugin(self, plugin_name: str) -> bool:
        """加载插件"""
        plugin_dir = Path(self.plugins_dir) / plugin_name
        
        if not plugin_dir.exists():
            return False
        
        # 加载插件入口文件
        entry_file = plugin_dir / "main.py"
        if entry_file.exists():
            try:
                spec = importlib.util.spec_from_file_location(
                    f"plugin_{plugin_name}",
                    str(entry_file)
                )
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                
                # 如果插件有 register 函数，调用它
                if hasattr(module, "register"):
                    module.register()
                
                return True
            except Exception as e:
                logger.error(f"Failed to load plugin {plugin_name}: {e}")
                return False
        
        return False
    
    def load_all_plugins(self):
        """加载所有插件"""
        plugins = self.discover_plugins()
        
        for plugin in plugins:
            if self.load_plugin(plugin.name):
                plugin.enabled = True
                self.plugins[plugin.name] = plugin
    
    def get_plugin_info(self) -> list[dict]:
        """获取所有插件信息"""
        return [
            {
                "name": p.name,
                "description": p.description,
                "version": p.version,
                "author": p.author,
                "enabled": p.enabled
            }
            for p in self.plugins.values()
        ]


# 技能系统
@dataclass
class Skill:
    """技能定义"""
    name: str
    description: str
    trigger_patterns: list[str]
    handler: Callable
    examples: list[str] = field(default_factory=list)


class SkillManager:
    """技能管理器"""
    
    def __init__(self):
        self.skills: dict[str, Skill] = {}
    
    def register_skill(self, skill: Skill):
        """注册技能"""
        self.skills[skill.name] = skill
    
    def find_skill(self, user_input: str) -> Optional[Skill]:
        """根据用户输入查找匹配的技能"""
        user_input_lower = user_input.lower()
        
        for skill in self.skills.values():
            for pattern in skill.trigger_patterns:
                if pattern.lower() in user_input_lower:
                    return skill
        
        return None
    
    def list_skills(self) -> list[dict]:
        """列出所有技能"""
        return [
            {
                "name": s.name,
                "description": s.description,
                "triggers": s.trigger_patterns,
                "examples": s.examples
            }
            for s in self.skills.values()
        ]


# 全局管理器
plugin_manager = PluginManager()
skill_manager = SkillManager()


# 内置技能示例
def register_builtin_skills():
    """注册内置技能"""
    
    # 代码审查技能
    skill_manager.register_skill(Skill(
        name="code_review",
        description="代码审查 - 分析代码质量、安全性和最佳实践",
        trigger_patterns=["review", "审查", "检查代码", "代码审查"],
        handler=None,  # 由 Agent 处理
        examples=[
            "帮我审查这个文件",
            "Review this code",
            "检查代码质量"
        ]
    ))
    
    # 重构技能
    skill_manager.register_skill(Skill(
        name="refactor",
        description="代码重构 - 优化代码结构和可读性",
        trigger_patterns=["refactor", "重构", "优化代码", "重写"],
        handler=None,
        examples=[
            "帮我重构这个函数",
            "优化这段代码",
            "Refactor this module"
        ]
    ))
    
    # 调试技能
    skill_manager.register_skill(Skill(
        name="debug",
        description="调试 - 帮助定位和修复 bug",
        trigger_patterns=["debug", "调试", "bug", "错误", "fix"],
        handler=None,
        examples=[
            "帮我调试这个错误",
            "这里有个 bug",
            "Debug this issue"
        ]
    ))
    
    # 测试技能
    skill_manager.register_skill(Skill(
        name="test",
        description="测试 - 编写和运行测试",
        trigger_patterns=["test", "测试", "单元测试", "pytest"],
        handler=None,
        examples=[
            "帮我写测试",
            "运行测试",
            "Write unit tests"
        ]
    ))


register_builtin_skills()
