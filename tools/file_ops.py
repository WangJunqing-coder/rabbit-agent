"""
文件操作工具 - 支持回滚记录
"""
import os
import json
from pathlib import Path
from typing import Optional

from tools.registry import tool
from rollback import get_rollback_manager


@tool(
    name="read_file",
    description="读取文件内容。支持文本文件，返回带行号的内容。",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "文件路径"},
            "offset": {"type": "integer", "description": "起始行号", "default": 1},
            "limit": {"type": "integer", "description": "读取行数", "default": 500}
        },
        "required": ["path"]
    }
)
async def read_file(path: str, offset: int = 1, limit: int = 500) -> dict:
    """读取文件内容"""
    try:
        file_path = Path(path).resolve()
        
        if not file_path.exists():
            return {"error": f"File not found: {path}"}
        
        if not file_path.is_file():
            return {"error": f"Not a file: {path}"}
        
        size = file_path.stat().st_size
        if size > 2_000_000:
            return {"error": f"File too large: {size} bytes"}
        
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        
        total_lines = len(lines)
        start = max(0, offset - 1)
        end = min(total_lines, start + limit)
        selected_lines = lines[start:end]
        
        numbered_lines = []
        for i, line in enumerate(selected_lines, start=start + 1):
            numbered_lines.append(f"{i:4d} | {line.rstrip()}")
        
        return {
            "content": "\n".join(numbered_lines),
            "total_lines": total_lines,
            "showing": f"{start + 1}-{end}"
        }
        
    except Exception as e:
        return {"error": str(e)}


@tool(
    name="write_file",
    description="创建或覆盖写入文件。会自动创建不存在的目录。",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "文件路径"},
            "content": {"type": "string", "description": "文件内容"}
        },
        "required": ["path", "content"]
    }
)
async def write_file(path: str, content: str) -> dict:
    """写入文件"""
    try:
        file_path = Path(path).resolve()
        rollback_mgr = get_rollback_manager()
        
        # 记录旧内容（用于回滚）
        old_content = None
        operation = "create"
        
        if file_path.exists():
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                old_content = f.read()
            operation = "modify"
        
        # 创建目录
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 写入文件
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
        
        # 记录变更
        rollback_mgr.record_file_change(
            path=str(file_path),
            operation=operation,
            old_content=old_content,
            new_content=content
        )
        
        return {
            "success": True,
            "path": str(file_path),
            "bytes_written": len(content.encode("utf-8")),
            "operation": operation
        }
        
    except Exception as e:
        return {"error": str(e)}


@tool(
    name="edit_file",
    description="编辑文件：查找并替换指定内容。",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "文件路径"},
            "old_text": {"type": "string", "description": "要查找的原始文本"},
            "new_text": {"type": "string", "description": "替换后的新文本"}
        },
        "required": ["path", "old_text", "new_text"]
    }
)
async def edit_file(path: str, old_text: str, new_text: str) -> dict:
    """编辑文件"""
    try:
        file_path = Path(path).resolve()
        rollback_mgr = get_rollback_manager()
        
        if not file_path.exists():
            return {"error": f"File not found: {path}"}
        
        # 读取原内容
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        
        if old_text not in content:
            return {
                "error": "Text not found in file",
                "hint": "Make sure the old_text matches exactly"
            }
        
        # 记录旧内容
        old_content = content
        
        # 替换
        new_content = content.replace(old_text, new_text, 1)
        
        # 写入文件
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(new_content)
        
        # 记录变更
        rollback_mgr.record_file_change(
            path=str(file_path),
            operation="modify",
            old_content=old_content,
            new_content=new_content
        )
        
        return {
            "success": True,
            "path": str(file_path),
            "replacements": 1
        }
        
    except Exception as e:
        return {"error": str(e)}


@tool(
    name="list_directory",
    description="列出目录内容。",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "目录路径", "default": "."},
            "pattern": {"type": "string", "description": "过滤模式", "default": "*"},
            "show_hidden": {"type": "boolean", "description": "是否显示隐藏文件", "default": False}
        }
    }
)
async def list_directory(path: str = ".", pattern: str = "*", show_hidden: bool = False) -> dict:
    """列出目录内容"""
    try:
        dir_path = Path(path).resolve()
        
        if not dir_path.exists():
            return {"error": f"Directory not found: {path}"}
        
        if not dir_path.is_dir():
            return {"error": f"Not a directory: {path}"}
        
        entries = []
        for item in sorted(dir_path.glob(pattern)):
            if not show_hidden and item.name.startswith("."):
                continue
            
            entry = {
                "name": item.name,
                "type": "directory" if item.is_dir() else "file",
            }
            
            if item.is_file():
                entry["size"] = item.stat().st_size
            
            entries.append(entry)
        
        return {
            "path": str(dir_path),
            "entries": entries,
            "total": len(entries)
        }
        
    except Exception as e:
        return {"error": str(e)}
