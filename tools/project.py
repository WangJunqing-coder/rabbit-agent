"""
项目上下文感知工具
"""
import json
import os
from pathlib import Path
from typing import Optional

from tools.registry import tool


@tool(
    name="project_detect",
    description="自动检测项目类型、框架、依赖等信息。支持 Python、Node.js、Java、Go、Rust 等。",
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "项目路径",
                "default": "."
            }
        }
    }
)
async def project_detect(path: str = ".") -> dict:
    """检测项目类型"""
    project_path = Path(path).resolve()
    
    if not project_path.exists():
        return {"error": f"Path not found: {path}"}
    
    result = {
        "path": str(project_path),
        "type": "unknown",
        "framework": None,
        "language": None,
        "package_manager": None,
        "config_files": [],
        "dependencies": []
    }
    
    # 检测配置文件
    config_patterns = {
        "python": ["requirements.txt", "setup.py", "pyproject.toml", "Pipfile", "poetry.lock"],
        "node": ["package.json", "package-lock.json", "yarn.lock", "pnpm-lock.yaml"],
        "java": ["pom.xml", "build.gradle", "build.gradle.kts"],
        "go": ["go.mod", "go.sum"],
        "rust": ["Cargo.toml", "Cargo.lock"],
        "dotnet": ["*.csproj", "*.sln"],
        "ruby": ["Gemfile", "Gemfile.lock"],
        "php": ["composer.json", "composer.lock"]
    }
    
    for lang, patterns in config_patterns.items():
        for pattern in patterns:
            matches = list(project_path.glob(pattern))
            if matches:
                result["language"] = lang
                result["config_files"].extend([m.name for m in matches])
    
    # Python 项目检测
    if (project_path / "requirements.txt").exists():
        result["type"] = "python"
        result["package_manager"] = "pip"
        try:
            with open(project_path / "requirements.txt", "r") as f:
                result["dependencies"] = [line.strip().split("==")[0] for line in f if line.strip() and not line.startswith("#")]
        except:
            pass
    
    elif (project_path / "pyproject.toml").exists():
        result["type"] = "python"
        result["package_manager"] = "poetry"
    
    # Node.js 项目检测
    elif (project_path / "package.json").exists():
        result["type"] = "node"
        result["package_manager"] = "npm"
        try:
            with open(project_path / "package.json", "r") as f:
                pkg = json.load(f)
                result["dependencies"] = list(pkg.get("dependencies", {}).keys())
                
                # 检测框架
                deps = pkg.get("dependencies", {})
                dev_deps = pkg.get("devDependencies", {})
                all_deps = {**deps, **dev_deps}
                
                if "react" in all_deps:
                    result["framework"] = "react"
                elif "vue" in all_deps:
                    result["framework"] = "vue"
                elif "next" in all_deps:
                    result["framework"] = "nextjs"
                elif "express" in all_deps:
                    result["framework"] = "express"
                elif "nestjs" in all_deps:
                    result["framework"] = "nestjs"
        except:
            pass
    
    # Go 项目检测
    elif (project_path / "go.mod").exists():
        result["type"] = "go"
        result["package_manager"] = "go modules"
    
    # Rust 项目检测
    elif (project_path / "Cargo.toml").exists():
        result["type"] = "rust"
        result["package_manager"] = "cargo"
    
    # Java 项目检测
    elif (project_path / "pom.xml").exists():
        result["type"] = "java"
        result["package_manager"] = "maven"
    elif (project_path / "build.gradle").exists():
        result["type"] = "java"
        result["package_manager"] = "gradle"
    
    return result


@tool(
    name="project_structure",
    description="显示项目目录结构，帮助理解项目组织方式。",
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "项目路径",
                "default": "."
            },
            "max_depth": {
                "type": "integer",
                "description": "最大深度",
                "default": 3
            },
            "ignore_patterns": {
                "type": "array",
                "items": {"type": "string"},
                "description": "忽略的目录/文件模式",
                "default": ["node_modules", "__pycache__", ".git", "venv", ".venv", "dist", "build"]
            }
        }
    }
)
async def project_structure(path: str = ".", max_depth: int = 3, ignore_patterns: list = None) -> dict:
    """显示项目结构"""
    if ignore_patterns is None:
        ignore_patterns = ["node_modules", "__pycache__", ".git", "venv", ".venv", "dist", "build"]
    
    project_path = Path(path).resolve()
    
    if not project_path.exists():
        return {"error": f"Path not found: {path}"}
    
    def should_ignore(name: str) -> bool:
        return any(pattern in name for pattern in ignore_patterns)
    
    def build_tree(current_path: Path, depth: int = 0) -> dict:
        if depth > max_depth:
            return {"name": current_path.name, "type": "dir", "truncated": True}
        
        if current_path.is_file():
            return {"name": current_path.name, "type": "file"}
        
        children = []
        try:
            for item in sorted(current_path.iterdir()):
                if should_ignore(item.name):
                    continue
                
                if item.is_dir():
                    children.append(build_tree(item, depth + 1))
                else:
                    children.append({"name": item.name, "type": "file"})
        except PermissionError:
            pass
        
        return {"name": current_path.name, "type": "dir", "children": children}
    
    tree = build_tree(project_path)
    return {"tree": tree}


@tool(
    name="project_readme",
    description="读取项目 README 文件，了解项目用途和说明。",
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "项目路径",
                "default": "."
            }
        }
    }
)
async def project_readme(path: str = ".") -> dict:
    """读取 README"""
    project_path = Path(path).resolve()
    
    # 尝试不同的 README 文件名
    readme_names = ["README.md", "README.rst", "README.txt", "README", "readme.md"]
    
    for name in readme_names:
        readme_path = project_path / name
        if readme_path.exists():
            try:
                with open(readme_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                return {"found": True, "file": name, "content": content[:3000]}
            except Exception as e:
                return {"error": str(e)}
    
    return {"found": False, "message": "No README file found"}
