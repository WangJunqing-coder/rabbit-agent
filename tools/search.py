"""
代码搜索工具
"""
import os
import subprocess
import asyncio
from pathlib import Path
from typing import Optional

from tools.registry import tool


@tool(
    name="search_files",
    description="搜索文件内容（类似 grep/ripgrep）。在指定目录中查找匹配的文本，返回匹配的行和文件路径。",
    parameters={
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "搜索模式（支持正则表达式）"
            },
            "path": {
                "type": "string",
                "description": "搜索目录，默认当前目录",
                "default": "."
            },
            "file_glob": {
                "type": "string",
                "description": "文件过滤（如 *.py, *.js）",
                "default": "*"
            },
            "ignore_case": {
                "type": "boolean",
                "description": "忽略大小写",
                "default": False
            },
            "max_results": {
                "type": "integer",
                "description": "最大结果数",
                "default": 50
            }
        },
        "required": ["pattern"]
    }
)
async def search_files(
    pattern: str,
    path: str = ".",
    file_glob: str = "*",
    ignore_case: bool = False,
    max_results: int = 50
) -> dict:
    """搜索文件内容"""
    try:
        search_path = Path(path).resolve()
        
        if not search_path.exists():
            return {"error": f"Path not found: {path}"}
        
        # 尝试使用 ripgrep，回退到 Python 实现
        try:
            return await _search_with_ripgrep(
                pattern, search_path, file_glob, ignore_case, max_results
            )
        except (FileNotFoundError, subprocess.SubprocessError):
            return await _search_with_python(
                pattern, search_path, file_glob, ignore_case, max_results
            )
        
    except Exception as e:
        return {"error": str(e)}


async def _search_with_ripgrep(
    pattern: str,
    path: Path,
    file_glob: str,
    ignore_case: bool,
    max_results: int
) -> dict:
    """使用 ripgrep 搜索"""
    cmd = ["rg", "--no-heading", "--line-number", "-m", str(max_results)]
    
    if ignore_case:
        cmd.append("-i")
    
    if file_glob and file_glob != "*":
        cmd.extend(["--glob", file_glob])
    
    cmd.extend([pattern, str(path)])
    
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
    
    output = stdout.decode("utf-8", errors="replace").strip()
    
    if not output:
        return {
            "pattern": pattern,
            "matches": [],
            "total": 0
        }
    
    matches = []
    for line in output.split("\n")[:max_results]:
        # ripgrep 输出格式: file:line:content
        # Windows 路径可能包含冒号 (C:\...)，需要特殊处理
        # 找到第一个冒号后跟数字的位置作为行号分隔符
        import re
        match = re.match(r'^(.+?):(\d+):(.*)$', line)
        if match:
            matches.append({
                "file": match.group(1),
                "line": int(match.group(2)),
                "content": match.group(3)
            })
    
    return {
        "pattern": pattern,
        "matches": matches,
        "total": len(matches)
    }


async def _search_with_python(
    pattern: str,
    path: Path,
    file_glob: str,
    ignore_case: bool,
    max_results: int
) -> dict:
    """Python 回退实现"""
    import re
    
    flags = re.IGNORECASE if ignore_case else 0
    try:
        regex = re.compile(pattern, flags)
    except re.error as e:
        return {"error": f"Invalid regex: {e}"}
    
    matches = []
    count = 0
    
    for file_path in path.rglob(file_glob):
        if not file_path.is_file():
            continue
        
        # 跳过二进制文件和隐藏目录
        if any(part.startswith(".") for part in file_path.parts):
            continue
        
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                for line_num, line in enumerate(f, 1):
                    if regex.search(line):
                        matches.append({
                            "file": str(file_path),
                            "line": line_num,
                            "content": line.rstrip()
                        })
                        count += 1
                        
                        if count >= max_results:
                            break
        except (PermissionError, OSError):
            continue
        
        if count >= max_results:
            break
    
    return {
        "pattern": pattern,
        "matches": matches,
        "total": len(matches)
    }


@tool(
    name="find_files",
    description="查找文件（类似 find）。按文件名模式查找文件。",
    parameters={
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "文件名模式（如 *.py, test_*.js）"
            },
            "path": {
                "type": "string",
                "description": "搜索目录",
                "default": "."
            },
            "max_depth": {
                "type": "integer",
                "description": "最大递归深度",
                "default": 10
            }
        },
        "required": ["pattern"]
    }
)
async def find_files(pattern: str, path: str = ".", max_depth: int = 10) -> dict:
    """查找文件"""
    try:
        search_path = Path(path).resolve()
        
        if not search_path.exists():
            return {"error": f"Path not found: {path}"}
        
        files = []
        
        def _search(current_path: Path, depth: int):
            if depth > max_depth:
                return
            
            try:
                for item in current_path.iterdir():
                    if item.name.startswith("."):
                        continue
                    
                    if item.match(pattern):
                        files.append({
                            "path": str(item),
                            "name": item.name,
                            "size": item.stat().st_size if item.is_file() else 0
                        })
                    
                    if item.is_dir():
                        _search(item, depth + 1)
            except PermissionError:
                pass
        
        _search(search_path, 0)
        
        return {
            "pattern": pattern,
            "files": files,
            "total": len(files)
        }
        
    except Exception as e:
        return {"error": str(e)}
