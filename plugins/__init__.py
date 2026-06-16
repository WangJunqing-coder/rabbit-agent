"""
插件/技能系统 - 可扩展的插件架构
支持从 skills/ 目录加载 SKILL.md 格式的技能
"""
import os
import re
import json
import importlib
import importlib.util
from pathlib import Path
from typing import Optional, Any, Callable
from dataclasses import dataclass, field


@dataclass
class Skill:
    """技能定义"""
    name: str
    description: str
    version: str = "1.0.0"
    author: str = ""
    
    # 触发条件
    triggers: list[str] = field(default_factory=list)  # 关键词触发
    patterns: list[str] = field(default_factory=list)   # 正则模式
    
    # 技能内容
    system_prompt: str = ""
    content: str = ""  # 完整的 SKILL.md 内容
    tools: list[str] = field(default_factory=list)
    
    # 元数据
    metadata: dict = field(default_factory=dict)
    
    # 来源
    source: str = "builtin"  # builtin, skillhub, custom


@dataclass
class Plugin:
    """插件定义"""
    name: str
    description: str
    version: str = "1.0.0"
    author: str = ""
    
    # 插件提供的功能
    skills: list[Skill] = field(default_factory=list)
    tools: dict[str, Callable] = field(default_factory=dict)
    
    # 生命周期钩子
    on_init: Optional[Callable] = None
    on_load: Optional[Callable] = None
    on_unload: Optional[Callable] = None
    
    # 元数据
    metadata: dict = field(default_factory=dict)


def parse_skill_md(content: str, filepath: str = "") -> Skill:
    """
    解析 SKILL.md 格式的技能文件
    
    格式：
    # 标题
    > 描述
    - triggers: 关键词1, 关键词2
    """
    lines = content.strip().split('\n')
    
    # 提取标题
    title = ""
    description = ""
    triggers = []
    author = ""
    version = "1.0.0"
    
    for i, line in enumerate(lines[:50]):  # 解析前50行
        line = line.strip()
        
        # 标题：第一个 # 开头的行
        if not title and line.startswith('#'):
            title = re.sub(r'^#+\s*', '', line).strip()
            # 移除 emoji 和特殊字符
            title = re.sub(r'[🧠🤖🔧💡✨📁🔌⚡️🚀🎯]', '', title).strip()
            title = title.split('·')[0].strip() if '·' in title else title
        
        # 描述：> 开头的行
        elif line.startswith('>'):
            desc_line = line.lstrip('> ').strip()
            if desc_line and not description:
                description = desc_line
            elif desc_line:
                description += " " + desc_line
        
        # 触发词 - 支持多种格式
        elif any(keyword in line.lower() for keyword in ['trigger', '触发', 'keywords', '关键词']):
            match = re.search(r'[:：]\s*(.+)', line)
            if match:
                triggers_str = match.group(1)
                triggers = [t.strip().strip('"\'') for t in re.split(r'[,，、|;；]', triggers_str) if t.strip()]
        
        # 版本
        elif 'version' in line.lower() or '版本' in line:
            match = re.search(r'[:：]\s*(\d+\.\d+\.\d+)', line)
            if match:
                version = match.group(1)
        
        # 作者
        elif 'author' in line.lower() or '作者' in line:
            match = re.search(r'[:：]\s*(.+)', line)
            if match:
                author = match.group(1).strip()
    
    # 如果没有提取到描述，使用前几行文本
    if not description:
        for line in lines[1:15]:
            line = line.strip()
            if line and not line.startswith('#') and not line.startswith('[') and len(line) > 10:
                description = line[:150]
                break
    
    # 从文件名提取名称
    if not title and filepath:
        title = Path(filepath).stem.replace('-', ' ').replace('_', ' ').title()
    
    # 生成触发词（如果没找到）
    if not triggers and title:
        # 从标题生成触发词
        words = re.findall(r'[a-zA-Z]+|[\u4e00-\u9fff]+', title.lower())
        triggers = [w for w in words if len(w) > 2][:5]
    
    # 从描述中提取更多触发词
    if description:
        # 提取关键功能词
        desc_words = re.findall(r'[a-zA-Z]{3,}|[\u4e00-\u9fff]{2,}', description)
        # 过滤常见停用词
        stop_words = {'the', 'and', 'for', 'with', 'that', 'this', 'from', 'have', 'are', 'was', 'were', 'been', 'being', '能够', '可以', '通过', '进行', '实现', '支持', '提供', '包含', '具有'}
        desc_keywords = [w for w in desc_words if w.lower() not in stop_words][:10]
        # 合并触发词，去重
        triggers = list(set(triggers + desc_keywords))[:15]
    
    # 对于 SkillHub 技能，添加通用开发触发词
    if filepath and 'skill' in str(filepath).lower():
        extra_triggers = ['设计', '开发', '创建', '构建', '实现', '编程', '代码', '项目', '应用', '系统',
                         'design', 'develop', 'create', 'build', 'implement', 'code', 'project', 'app', 'system',
                         'UI', 'UX', '前端', '后端', '全栈', 'frontend', 'backend', 'fullstack']
        triggers = list(set(triggers + extra_triggers))[:20]
    
    return Skill(
        name=title or "Unknown Skill",
        description=description[:300] if description else "No description",
        version=version,
        author=author,
        triggers=triggers,
        content=content,
        system_prompt=content[:3000] if len(content) > 3000 else content,
        source="skillhub"
    )


class PluginManager:
    """插件管理器"""
    
    def __init__(self, plugins_dir: str = None, skills_dir: str = None):
        if plugins_dir is None:
            plugins_dir = os.path.join(str(Path.home()), ".liteagent", "plugins")
        
        if skills_dir is None:
            # 默认使用项目目录下的 skills 文件夹
            skills_dir = os.path.join(os.getcwd(), "skills")
        
        self.plugins_dir = Path(plugins_dir)
        self.skills_dir = Path(skills_dir)
        
        self.plugins_dir.mkdir(parents=True, exist_ok=True)
        self.skills_dir.mkdir(parents=True, exist_ok=True)
        
        self.plugins: dict[str, Plugin] = {}
        self.skills: dict[str, Skill] = {}
        
        # 加载内置技能
        self._load_builtin_skills()
        
        # 加载 SKILL.md 格式的技能
        self._load_skill_md_files()
    
    def _load_builtin_skills(self):
        """加载内置技能"""
        # Python 技能
        self.register_skill(Skill(
            name="python_expert",
            description="Python 编程专家，擅长 Python 代码编写、调试和优化",
            triggers=["python", "py", "pip", "virtualenv", "conda"],
            system_prompt="""你是一个 Python 编程专家。遵循以下最佳实践：
- 使用类型提示
- 编写清晰的文档字符串
- 遵循 PEP 8 规范
- 优先使用标准库
- 编写可测试的代码""",
            source="builtin"
        ))
        
        # JavaScript 技能
        self.register_skill(Skill(
            name="javascript_expert",
            description="JavaScript/TypeScript 编程专家",
            triggers=["javascript", "typescript", "js", "ts", "npm", "node"],
            system_prompt="""你是一个 JavaScript/TypeScript 编程专家。遵循以下最佳实践：
- 使用 TypeScript 进行类型安全
- 使用 ES6+ 语法
- 遵循 ESLint 规范
- 编写清晰的异步代码
- 使用现代框架最佳实践""",
            source="builtin"
        ))
        
        # Git 技能
        self.register_skill(Skill(
            name="git_expert",
            description="Git 版本控制专家",
            triggers=["git", "commit", "branch", "merge", "rebase", "pull request"],
            system_prompt="""你是一个 Git 版本控制专家。帮助用户：
- 理解 Git 工作流
- 解决合并冲突
- 优化提交历史
- 使用分支策略
- 代码审查最佳实践""",
            source="builtin"
        ))
        
        # 调试技能
        self.register_skill(Skill(
            name="debugger",
            description="代码调试专家",
            triggers=["debug", "error", "bug", "fix", "traceback", "exception"],
            system_prompt="""你是一个代码调试专家。按照以下步骤调试：
1. 理解错误信息
2. 定位问题根源
3. 分析可能的原因
4. 提出修复方案
5. 验证修复效果""",
            source="builtin"
        ))
        
        # 代码审查技能
        self.register_skill(Skill(
            name="code_reviewer",
            description="代码审查专家",
            triggers=["review", "code review", "检查", "审查"],
            system_prompt="""你是一个代码审查专家。审查以下方面：
- 代码风格和规范
- 潜在的 bug
- 性能问题
- 安全漏洞
- 可维护性
- 测试覆盖""",
            source="builtin"
        ))
    
    def _load_skill_md_files(self):
        """加载 SKILL.md 格式的技能文件"""
        if not self.skills_dir.exists():
            return
        
        for item in self.skills_dir.iterdir():
            if item.is_dir():
                # 检查目录中的 SKILL.md 文件
                skill_file = item / "SKILL.md"
                if skill_file.exists():
                    try:
                        self._load_skill_from_file(skill_file)
                    except Exception as e:
                        print(f"Warning: Failed to load skill from {skill_file}: {e}")
            
            elif item.is_file() and item.suffix == '.md' and item.name != 'README.md':
                # 直接加载 .md 文件
                try:
                    self._load_skill_from_file(item)
                except Exception as e:
                    print(f"Warning: Failed to load skill from {item}: {e}")
    
    def _load_skill_from_file(self, filepath: Path):
        """从文件加载技能"""
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        skill = parse_skill_md(content, str(filepath))
        
        # 使用目录名或文件名作为技能 ID
        if filepath.name == "SKILL.md":
            skill_id = filepath.parent.name
        else:
            skill_id = filepath.stem
        
        skill.name = skill_id  # 使用目录名作为技能名称
        self.register_skill(skill)
    
    def register_plugin(self, plugin: Plugin):
        """注册插件"""
        self.plugins[plugin.name] = plugin
        
        # 注册插件提供的技能
        for skill in plugin.skills:
            self.register_skill(skill)
        
        # 调用加载钩子
        if plugin.on_load:
            plugin.on_load()
    
    def register_skill(self, skill: Skill):
        """注册技能"""
        self.skills[skill.name] = skill
    
    def unregister_plugin(self, name: str):
        """注销插件"""
        if name in self.plugins:
            plugin = self.plugins[name]
            
            # 调用卸载钩子
            if plugin.on_unload:
                plugin.on_unload()
            
            # 移除技能
            for skill in plugin.skills:
                if skill.name in self.skills:
                    del self.skills[skill.name]
            
            del self.plugins[name]
    
    def match_skill(self, text: str) -> Optional[Skill]:
        """根据文本匹配技能"""
        text_lower = text.lower()
        
        for skill in self.skills.values():
            # 检查触发词
            for trigger in skill.triggers:
                if trigger.lower() in text_lower:
                    return skill
            
            # 检查正则模式
            for pattern in skill.patterns:
                if re.search(pattern, text, re.IGNORECASE):
                    return skill
        
        return None
    
    def get_skill_prompt(self, skill_name: str) -> str:
        """获取技能系统提示"""
        skill = self.skills.get(skill_name)
        if skill and skill.system_prompt:
            return f"\n## 当前技能: {skill.name}\n{skill.system_prompt}"
        return ""
    
    def list_plugins(self) -> list[dict]:
        """列出所有插件"""
        return [
            {
                "name": p.name,
                "description": p.description,
                "version": p.version,
                "skills": [s.name for s in p.skills]
            }
            for p in self.plugins.values()
        ]
    
    def list_skills(self) -> list[dict]:
        """列出所有技能"""
        return [
            {
                "name": s.name,
                "description": s.description[:50] if s.description else "",
                "triggers": s.triggers[:5] if s.triggers else [],
                "source": s.source
            }
            for s in self.skills.values()
        ]
    
    def get_skill_content(self, skill_name: str) -> Optional[str]:
        """获取技能完整内容"""
        skill = self.skills.get(skill_name)
        return skill.content if skill else None
    
    def load_plugins_from_dir(self):
        """从目录加载插件"""
        for item in self.plugins_dir.iterdir():
            if item.is_dir():
                plugin_file = item / "plugin.py"
                manifest_file = item / "manifest.json"
                
                if plugin_file.exists() and manifest_file.exists():
                    try:
                        self._load_plugin_from_dir(item)
                    except Exception as e:
                        print(f"Failed to load plugin {item.name}: {e}")
    
    def _load_plugin_from_dir(self, plugin_dir: Path):
        """从目录加载单个插件"""
        # 读取 manifest
        with open(plugin_dir / "manifest.json", "r", encoding="utf-8") as f:
            manifest = json.load(f)
        
        # 加载插件模块
        spec = importlib.util.spec_from_file_location(
            f"plugin_{plugin_dir.name}",
            plugin_dir / "plugin.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        
        # 获取插件实例
        if hasattr(module, "create_plugin"):
            plugin = module.create_plugin()
            self.register_plugin(plugin)


# 全局插件管理器
_plugin_manager: Optional[PluginManager] = None


def get_plugin_manager() -> PluginManager:
    """获取插件管理器"""
    global _plugin_manager
    if _plugin_manager is None:
        _plugin_manager = PluginManager()
        _plugin_manager.load_plugins_from_dir()
    return _plugin_manager


def create_skill(
    name: str,
    description: str,
    triggers: list[str] = None,
    system_prompt: str = "",
    tools: list[str] = None
) -> Skill:
    """创建技能"""
    return Skill(
        name=name,
        description=description,
        triggers=triggers or [],
        system_prompt=system_prompt,
        tools=tools or []
    )


def create_plugin(
    name: str,
    description: str,
    skills: list[Skill] = None,
    tools: dict[str, Callable] = None
) -> Plugin:
    """创建插件"""
    return Plugin(
        name=name,
        description=description,
        skills=skills or [],
        tools=tools or {}
    )
