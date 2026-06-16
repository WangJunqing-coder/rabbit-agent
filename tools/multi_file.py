"""
多文件编辑协调工具
"""
import json
import asyncio
from pathlib import Path
from typing import Optional

from tools.registry import tool


@tool(
    name="batch_edit",
    description="批量编辑多个文件。一次操作修改多个文件，支持查找替换、正则替换等。",
    parameters={
        "type": "object",
        "properties": {
            "edits": {
                "type": "array",
                "description": "编辑操作列表",
                "items": {
                    "type": "object",
                    "properties": {
                        "file": {"type": "string", "description": "文件路径"},
                        "old_text": {"type": "string", "description": "查找文本"},
                        "new_text": {"type": "string", "description": "替换文本"}
                    },
                    "required": ["file", "old_text", "new_text"]
                }
            },
            "dry_run": {
                "type": "boolean",
                "description": "试运行，不实际修改",
                "default": False
            }
        },
        "required": ["edits"]
    }
)
async def batch_edit(edits: list, dry_run: bool = False) -> dict:
    """批量编辑"""
    results = []
    errors = []
    
    for i, edit in enumerate(edits):
        file_path = Path(edit["file"]).resolve()
        old_text = edit["old_text"]
        new_text = edit["new_text"]
        
        if not file_path.exists():
            errors.append({"index": i, "file": edit["file"], "error": "File not found"})
            continue
        
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            
            if old_text not in content:
                errors.append({"index": i, "file": edit["file"], "error": "Text not found"})
                continue
            
            count = content.count(old_text)
            
            if not dry_run:
                new_content = content.replace(old_text, new_text)
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(new_content)
            
            results.append({
                "index": i,
                "file": edit["file"],
                "replacements": count,
                "status": "preview" if dry_run else "done"
            })
            
        except Exception as e:
            errors.append({"index": i, "file": edit["file"], "error": str(e)})
    
    return {
        "total": len(edits),
        "success": len(results),
        "failed": len(errors),
        "dry_run": dry_run,
        "results": results,
        "errors": errors
    }


@tool(
    name="refactor_rename",
    description="重命名变量/函数/类，支持跨文件重构。自动更新所有引用。",
    parameters={
        "type": "object",
        "properties": {
            "old_name": {
                "type": "string",
                "description": "原名称"
            },
            "new_name": {
                "type": "string",
                "description": "新名称"
            },
            "path": {
                "type": "string",
                "description": "搜索路径",
                "default": "."
            },
            "file_glob": {
                "type": "string",
                "description": "文件过滤",
                "default": "*.py"
            },
            "dry_run": {
                "type": "boolean",
                "description": "试运行",
                "default": True
            }
        },
        "required": ["old_name", "new_name"]
    }
)
async def refactor_rename(old_name: str, new_name: str, path: str = ".", file_glob: str = "*.py", dry_run: bool = True) -> dict:
    """重命名重构"""
    import re
    
    project_path = Path(path).resolve()
    
    # 查找所有包含旧名称的文件
    affected_files = []
    
    for file_path in project_path.rglob(file_glob):
        if file_path.is_file() and "__pycache__" not in str(file_path):
            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                
                # 使用单词边界匹配
                pattern = r'\b' + re.escape(old_name) + r'\b'
                matches = re.findall(pattern, content)
                
                if matches:
                    affected_files.append({
                        "file": str(file_path),
                        "occurrences": len(matches)
                    })
                    
                    if not dry_run:
                        new_content = re.sub(pattern, new_name, content)
                        with open(file_path, "w", encoding="utf-8") as f:
                            f.write(new_content)
                            
            except Exception:
                continue
    
    return {
        "old_name": old_name,
        "new_name": new_name,
        "affected_files": affected_files,
        "total_files": len(affected_files),
        "total_occurrences": sum(f["occurrences"] for f in affected_files),
        "dry_run": dry_run
    }


@tool(
    name="create_files",
    description="一次性创建多个文件。用于快速搭建项目结构。",
    parameters={
        "type": "object",
        "properties": {
            "files": {
                "type": "array",
                "description": "文件列表",
                "items": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "文件路径"},
                        "content": {"type": "string", "description": "文件内容"}
                    },
                    "required": ["path", "content"]
                }
            }
        },
        "required": ["files"]
    }
)
async def create_files(files: list) -> dict:
    """批量创建文件"""
    results = []
    errors = []
    
    for file_info in files:
        file_path = Path(file_info["path"]).resolve()
        content = file_info["content"]
        
        try:
            # 创建目录
            file_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)
            
            results.append({
                "path": str(file_path),
                "size": len(content.encode("utf-8")),
                "status": "created"
            })
        except Exception as e:
            errors.append({
                "path": file_info["path"],
                "error": str(e)
            })
    
    return {
        "total": len(files),
        "created": len(results),
        "failed": len(errors),
        "results": results,
        "errors": errors
    }
