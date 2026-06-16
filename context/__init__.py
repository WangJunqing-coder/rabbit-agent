"""
项目上下文感知 - 自动检测项目类型、技术栈、依赖等
"""
import os
import json
import re
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field


@dataclass
class ProjectInfo:
    """项目信息"""
    name: str
    path: str
    type: str  # python, node, rust, go, java, etc.
    description: str = ""
    version: str = ""
    
    # 技术栈
    language: str = ""
    framework: str = ""
    dependencies: list[str] = field(default_factory=list)
    dev_dependencies: list[str] = field(default_factory=list)
    
    # 项目结构
    entry_point: str = ""
    src_dirs: list[str] = field(default_factory=list)
    test_dirs: list[str] = field(default_factory=list)
    config_files: list[str] = field(default_factory=list)
    
    # Git 信息
    has_git: bool = False
    git_branch: str = ""
    git_remote: str = ""
    
    # 元数据
    metadata: dict = field(default_factory=dict)


class ProjectDetector:
    """项目类型检测器"""
    
    # 项目类型特征文件
    PROJECT_MARKERS = {
        "python": {
            "files": ["setup.py", "pyproject.toml", "requirements.txt", "Pipfile", "poetry.lock"],
            "dirs": ["__pycache__", ".venv", "venv"],
        },
        "node": {
            "files": ["package.json", "tsconfig.json", "yarn.lock", "package-lock.json", "pnpm-lock.yaml"],
            "dirs": ["node_modules", ".next", "dist"],
        },
        "rust": {
            "files": ["Cargo.toml", "Cargo.lock"],
            "dirs": ["target"],
        },
        "go": {
            "files": ["go.mod", "go.sum"],
            "dirs": ["vendor"],
        },
        "java": {
            "files": ["pom.xml", "build.gradle", "build.gradle.kts", "settings.gradle"],
            "dirs": ["src/main", "src/test", "target", "build"],
        },
        "dotnet": {
            "files": ["*.csproj", "*.sln", "*.fsproj"],
            "dirs": ["bin", "obj"],
        },
        "ruby": {
            "files": ["Gemfile", "Gemfile.lock", "*.gemspec"],
            "dirs": [".bundle"],
        },
        "php": {
            "files": ["composer.json", "composer.lock"],
            "dirs": ["vendor"],
        },
    }
    
    # 框架检测
    FRAMEWORK_MARKERS = {
        "python": {
            "django": ["manage.py", "settings.py", "wsgi.py"],
            "flask": ["app.py", "wsgi.py"],
            "fastapi": ["main.py"],
            "streamlit": ["streamlit_app.py"],
        },
        "node": {
            "react": ["src/App.tsx", "src/App.jsx", "public/index.html"],
            "vue": ["src/App.vue", "vue.config.js"],
            "angular": ["angular.json", "src/app/app.module.ts"],
            "next": ["next.config.js", "pages/"],
            "nuxt": ["nuxt.config.js", "nuxt.config.ts"],
            "express": ["app.js", "server.js"],
        },
    }
    
    def __init__(self, root_path: str = None):
        self.root_path = Path(root_path or os.getcwd())
    
    def detect(self) -> ProjectInfo:
        """检测项目信息"""
        # 先检测类型
        project_type = self._detect_type()
        framework = self._detect_framework(project_type)
        
        info = ProjectInfo(
            name=self.root_path.name,
            path=str(self.root_path),
            type=project_type,
            language=project_type,
            framework=framework
        )
        
        # 读取项目元数据
        self._read_metadata(info)
        
        # 检测项目结构
        self._detect_structure(info)
        
        # 检测 Git 信息
        self._detect_git(info)
        
        return info
    
    def _detect_type(self) -> str:
        """检测项目类型"""
        scores = {}
        
        for lang, markers in self.PROJECT_MARKERS.items():
            score = 0
            
            # 检查特征文件
            for file_pattern in markers["files"]:
                if "*" in file_pattern:
                    # 通配符匹配
                    if list(self.root_path.glob(file_pattern)):
                        score += 2
                else:
                    if (self.root_path / file_pattern).exists():
                        score += 2
            
            # 检查特征目录
            for dir_name in markers["dirs"]:
                if (self.root_path / dir_name).is_dir():
                    score += 1
            
            if score > 0:
                scores[lang] = score
        
        if not scores:
            # 尝试通过文件扩展名检测
            return self._detect_by_extensions()
        
        return max(scores, key=scores.get)
    
    def _detect_by_extensions(self) -> str:
        """通过文件扩展名检测"""
        ext_count = {}
        
        for file in self.root_path.rglob("*"):
            if file.is_file() and not any(p.startswith(".") for p in file.parts):
                ext = file.suffix.lower()
                if ext in [".py", ".js", ".ts", ".rs", ".go", ".java", ".cs", ".rb", ".php"]:
                    ext_count[ext] = ext_count.get(ext, 0) + 1
        
        if not ext_count:
            return "unknown"
        
        ext_to_lang = {
            ".py": "python",
            ".js": "node",
            ".ts": "node",
            ".rs": "rust",
            ".go": "go",
            ".java": "java",
            ".cs": "dotnet",
            ".rb": "ruby",
            ".php": "php",
        }
        
        max_ext = max(ext_count, key=ext_count.get)
        return ext_to_lang.get(max_ext, "unknown")
    
    def _detect_framework(self, language: str) -> str:
        """检测框架"""
        frameworks = self.FRAMEWORK_MARKERS.get(language, {})
        
        for framework, markers in frameworks.items():
            for marker in markers:
                if "/" in marker:
                    # 路径形式
                    if (self.root_path / marker).exists():
                        return framework
                else:
                    # 文件名形式
                    if (self.root_path / marker).exists():
                        return framework
        
        # 特殊检测：通过依赖文件内容判断
        return self._detect_framework_from_deps(language)
    
    def _detect_framework_from_deps(self, language: str) -> str:
        """从依赖文件检测框架"""
        if language == "python":
            req_file = self.root_path / "requirements.txt"
            if req_file.exists():
                content = req_file.read_text(encoding="utf-8", errors="ignore").lower()
                if "django" in content:
                    return "django"
                elif "flask" in content:
                    return "flask"
                elif "fastapi" in content:
                    return "fastapi"
                elif "streamlit" in content:
                    return "streamlit"
        
        elif language == "node":
            pkg_file = self.root_path / "package.json"
            if pkg_file.exists():
                try:
                    with open(pkg_file, "r", encoding="utf-8") as f:
                        pkg = json.load(f)
                    
                    deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
                    
                    if "react" in deps:
                        return "react"
                    elif "vue" in deps:
                        return "vue"
                    elif "@angular/core" in deps:
                        return "angular"
                    elif "next" in deps:
                        return "next"
                    elif "nuxt" in deps:
                        return "nuxt"
                    elif "express" in deps:
                        return "express"
                except (json.JSONDecodeError, KeyError):
                    pass
        
        return ""
    
    def _read_metadata(self, info: ProjectInfo):
        """读取项目元数据"""
        if info.type == "python":
            self._read_python_metadata(info)
        elif info.type == "node":
            self._read_node_metadata(info)
        elif info.type == "rust":
            self._read_rust_metadata(info)
        elif info.type == "go":
            self._read_go_metadata(info)
    
    def _read_python_metadata(self, info: ProjectInfo):
        """读取 Python 项目元数据"""
        # pyproject.toml
        pyproject = self.root_path / "pyproject.toml"
        if pyproject.exists():
            try:
                import tomllib
                with open(pyproject, "rb") as f:
                    data = tomllib.load(f)
                
                project = data.get("project", {})
                info.name = project.get("name", info.name)
                info.description = project.get("description", "")
                info.version = project.get("version", "")
                
                deps = project.get("dependencies", [])
                info.dependencies = [d.split(">=")[0].split("==")[0].split("<")[0].strip() for d in deps]
            except Exception:
                pass
        
        # setup.py
        setup_py = self.root_path / "setup.py"
        if setup_py.exists() and not info.name:
            content = setup_py.read_text(encoding="utf-8", errors="ignore")
            name_match = re.search(r"name\s*=\s*['\"]([^'\"]+)['\"]", content)
            if name_match:
                info.name = name_match.group(1)
        
        # requirements.txt
        req_file = self.root_path / "requirements.txt"
        if req_file.exists():
            content = req_file.read_text(encoding="utf-8", errors="ignore")
            deps = []
            for line in content.splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    dep = line.split(">=")[0].split("==")[0].split("<")[0].strip()
                    deps.append(dep)
            if not info.dependencies:
                info.dependencies = deps
    
    def _read_node_metadata(self, info: ProjectInfo):
        """读取 Node.js 项目元数据"""
        pkg_file = self.root_path / "package.json"
        if pkg_file.exists():
            try:
                with open(pkg_file, "r", encoding="utf-8") as f:
                    pkg = json.load(f)
                
                info.name = pkg.get("name", info.name)
                info.description = pkg.get("description", "")
                info.version = pkg.get("version", "")
                
                info.dependencies = list(pkg.get("dependencies", {}).keys())
                info.dev_dependencies = list(pkg.get("devDependencies", {}).keys())
                
                # 检测入口文件
                if "main" in pkg:
                    info.entry_point = pkg["main"]
                elif "scripts" in pkg and "start" in pkg["scripts"]:
                    start_cmd = pkg["scripts"]["start"]
                    if "node" in start_cmd:
                        parts = start_cmd.split()
                        if len(parts) > 1:
                            info.entry_point = parts[-1]
            except (json.JSONDecodeError, KeyError):
                pass
    
    def _read_rust_metadata(self, info: ProjectInfo):
        """读取 Rust 项目元数据"""
        cargo = self.root_path / "Cargo.toml"
        if cargo.exists():
            try:
                import tomllib
                with open(cargo, "rb") as f:
                    data = tomllib.load(f)
                
                package = data.get("package", {})
                info.name = package.get("name", info.name)
                info.description = package.get("description", "")
                info.version = package.get("version", "")
                
                deps = data.get("dependencies", {})
                info.dependencies = list(deps.keys())
            except Exception:
                pass
    
    def _read_go_metadata(self, info: ProjectInfo):
        """读取 Go 项目元数据"""
        go_mod = self.root_path / "go.mod"
        if go_mod.exists():
            content = go_mod.read_text(encoding="utf-8", errors="ignore")
            
            # 解析 module 名
            module_match = re.search(r"^module\s+(.+)$", content, re.MULTILINE)
            if module_match:
                info.name = module_match.group(1).split("/")[-1]
            
            # 解析依赖
            deps = []
            for match in re.finditer(r"^\s+(\S+)\s+", content, re.MULTILINE):
                dep = match.group(1)
                if not dep.startswith("module") and not dep.startswith("go"):
                    deps.append(dep)
            info.dependencies = deps
    
    def _detect_structure(self, info: ProjectInfo):
        """检测项目结构"""
        common_src_dirs = ["src", "lib", "app", "pkg", "internal", "cmd"]
        common_test_dirs = ["tests", "test", "__tests__", "spec"]
        common_config_files = [
            "config.json", "config.yaml", "config.yml", ".env",
            ".env.local", ".env.production", "settings.py"
        ]
        
        for d in common_src_dirs:
            if (self.root_path / d).is_dir():
                info.src_dirs.append(d)
        
        for d in common_test_dirs:
            if (self.root_path / d).is_dir():
                info.test_dirs.append(d)
        
        for f in common_config_files:
            if (self.root_path / f).exists():
                info.config_files.append(f)
        
        # 检测入口文件
        if not info.entry_point:
            common_entries = ["main.py", "app.py", "index.js", "main.js", "index.ts", "main.ts", "main.go", "src/main.rs"]
            for entry in common_entries:
                if (self.root_path / entry).exists():
                    info.entry_point = entry
                    break
    
    def _detect_git(self, info: ProjectInfo):
        """检测 Git 信息"""
        git_dir = self.root_path / ".git"
        if git_dir.is_dir():
            info.has_git = True
            
            # 获取当前分支
            head_file = git_dir / "HEAD"
            if head_file.exists():
                content = head_file.read_text(encoding="utf-8", errors="ignore").strip()
                if content.startswith("ref: refs/heads/"):
                    info.git_branch = content.split("/")[-1]
            
            # 获取 remote
            config_file = git_dir / "config"
            if config_file.exists():
                content = config_file.read_text(encoding="utf-8", errors="ignore")
                remote_match = re.search(r"url\s*=\s*(.+)", content)
                if remote_match:
                    info.git_remote = remote_match.group(1).strip()


def get_project_context(root_path: str = None) -> str:
    """获取项目上下文描述（用于系统提示）"""
    detector = ProjectDetector(root_path)
    info = detector.detect()
    
    parts = []
    parts.append(f"## 项目信息")
    parts.append(f"- 项目名称: {info.name}")
    parts.append(f"- 项目类型: {info.type}")
    
    if info.framework:
        parts.append(f"- 框架: {info.framework}")
    
    if info.description:
        parts.append(f"- 描述: {info.description}")
    
    if info.version:
        parts.append(f"- 版本: {info.version}")
    
    if info.entry_point:
        parts.append(f"- 入口文件: {info.entry_point}")
    
    if info.src_dirs:
        parts.append(f"- 源码目录: {', '.join(info.src_dirs)}")
    
    if info.test_dirs:
        parts.append(f"- 测试目录: {', '.join(info.test_dirs)}")
    
    if info.dependencies:
        deps_str = ", ".join(info.dependencies[:10])
        if len(info.dependencies) > 10:
            deps_str += f" 等 {len(info.dependencies)} 个"
        parts.append(f"- 主要依赖: {deps_str}")
    
    if info.has_git:
        parts.append(f"- Git 分支: {info.git_branch}")
        if info.git_remote:
            parts.append(f"- Git 远程: {info.git_remote}")
    
    if info.config_files:
        parts.append(f"- 配置文件: {', '.join(info.config_files)}")
    
    return "\n".join(parts)
