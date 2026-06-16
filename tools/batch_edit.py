"""
多文件编辑工具 - 支持批量编辑多个文件
"""
import os
import json
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field

from tools.registry import tool


@dataclass
class FileChange:
    """文件变更记录"""
    path: str
    operation: str  # create, modify, delete
    old_content: Optional[str] = None
    new_content: Optional[str] = None
    diff: Optional[str] = None


class EditPlan:
    """编辑计划"""
    
    def __init__(self):
        self.changes: list[FileChange] = []
        self.applied: list[FileChange] = []
        self.failed: list[tuple[FileChange, str]] = []
    
    def add_change(self, change: FileChange):
        """添加变更"""
        self.changes.append(change)
    
    def preview(self) -> str:
        """预览所有变更"""
        lines = ["## 编辑计划预览\n"]
        
        for i, change in enumerate(self.changes, 1):
            lines.append(f"### {i}. {change.operation.upper()}: {change.path}")
            
            if change.operation == "create":
                lines.append(f"  - 创建新文件")
                if change.new_content:
                    preview = change.new_content[:200]
                    if len(change.new_content) > 200:
                        preview += "..."
                    lines.append(f"  - 内容预览: {preview}")
            
            elif change.operation == "modify":
                lines.append(f"  - 修改文件")
                if change.diff:
                    lines.append(f"  - 变更:\n{change.diff}")
            
            elif change.operation == "delete":
                lines.append(f"  - 删除文件")
            
            lines.append("")
        
        return "\n".join(lines)
    
    def apply(self, dry_run: bool = False) -> dict:
        """应用所有变更"""
        self.applied = []
        self.failed = []
        
        for change in self.changes:
            try:
                if dry_run:
                    # 仅验证，不实际修改
                    if change.operation in ["modify", "delete"]:
                        if not Path(change.path).exists():
                            raise FileNotFoundError(f"File not found: {change.path}")
                    elif change.operation == "create":
                        if Path(change.path).exists():
                            raise FileExistsError(f"File already exists: {change.path}")
                else:
                    # 实际应用变更
                    if change.operation == "create":
                        Path(change.path).parent.mkdir(parents=True, exist_ok=True)
                        with open(change.path, "w", encoding="utf-8") as f:
                            f.write(change.new_content or "")
                    
                    elif change.operation == "modify":
                        with open(change.path, "w", encoding="utf-8") as f:
                            f.write(change.new_content or "")
                    
                    elif change.operation == "delete":
                        Path(change.path).unlink()
                
                self.applied.append(change)
            
            except Exception as e:
                self.failed.append((change, str(e)))
        
        return {
            "total": len(self.changes),
            "applied": len(self.applied),
            "failed": len(self.failed),
            "details": {
                "applied": [{"path": c.path, "op": c.operation} for c in self.applied],
                "failed": [{"path": c.path, "op": c.operation, "error": e} for c, e in self.failed]
            }
        }
    
    def rollback(self):
        """回滚已应用的变更"""
        for change in reversed(self.applied):
            try:
                if change.operation == "create":
                    Path(change.path).unlink(missing_ok=True)
                elif change.operation == "modify":
                    if change.old_content is not None:
                        with open(change.path, "w", encoding="utf-8") as f:
                            f.write(change.old_content)
                elif change.operation == "delete":
                    if change.old_content is not None:
                        with open(change.path, "w", encoding="utf-8") as f:
                            f.write(change.old_content)
            except Exception:
                pass
        
        self.applied = []


@tool(
    name="batch_edit",
    description="批量编辑多个文件。可以同时创建、修改、删除多个文件，支持预览和回滚。",
    parameters={
        "type": "object",
        "properties": {
            "changes": {
                "type": "array",
                "description": "变更列表",
                "items": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "文件路径"},
                        "operation": {"type": "string", "enum": ["create", "modify", "delete"], "description": "操作类型"},
                        "content": {"type": "string", "description": "文件内容（create/modify 时必填）"}
                    },
                    "required": ["path", "operation"]
                }
            },
            "dry_run": {
                "type": "boolean",
                "description": "是否仅预览不实际修改",
                "default": False
            }
        },
        "required": ["changes"]
    }
)
async def batch_edit(changes: list[dict], dry_run: bool = False) -> dict:
    """批量编辑文件"""
    plan = EditPlan()
    
    for change in changes:
        path = change["path"]
        operation = change["operation"]
        content = change.get("content", "")
        
        # 读取原内容（用于回滚）
        old_content = None
        if Path(path).exists():
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                old_content = f.read()
        
        plan.add_change(FileChange(
            path=path,
            operation=operation,
            old_content=old_content,
            new_content=content if operation in ["create", "modify"] else None
        ))
    
    # 应用变更
    result = plan.apply(dry_run=dry_run)
    
    if dry_run:
        result["preview"] = plan.preview()
    
    return result


@tool(
    name="apply_patch",
    description="应用 diff/patch 到文件。支持标准 unified diff 格式。",
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "目标文件路径"
            },
            "patch": {
                "type": "string",
                "description": "unified diff 格式的 patch 内容"
            },
            "reverse": {
                "type": "boolean",
                "description": "是否反向应用 patch",
                "default": False
            }
        },
        "required": ["path", "patch"]
    }
)
async def apply_patch(path: str, patch: str, reverse: bool = False) -> dict:
    """应用 patch"""
    try:
        file_path = Path(path)
        if not file_path.exists():
            return {"error": f"File not found: {path}"}
        
        # 读取原内容
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        
        lines = content.splitlines(keepends=True)
        patch_lines = patch.splitlines()
        
        # 简单的 patch 应用（支持 @@ -old +new @@ 格式）
        result_lines = []
        i = 0
        patch_idx = 0
        
        while patch_idx < len(patch_lines):
            line = patch_lines[patch_idx]
            
            if line.startswith("@@"):
                # 解析 hunk header
                import re
                match = re.match(r"@@ -(\d+),?\d* \+(\d+),?\d* @@", line)
                if match:
                    old_start = int(match.group(1)) - 1
                    new_start = int(match.group(2)) - 1
                    
                    # 跳过 hunk header
                    patch_idx += 1
                    
                    # 应用 hunk
                    while patch_idx < len(patch_lines) and not patch_lines[patch_idx].startswith("@@"):
                        hunk_line = patch_lines[patch_idx]
                        
                        if hunk_line.startswith("-"):
                            if reverse:
                                result_lines.append(hunk_line[1:])
                            # 跳过删除的行
                            i += 1
                        elif hunk_line.startswith("+"):
                            if not reverse:
                                result_lines.append(hunk_line[1:])
                        else:
                            # 上下文行
                            if i < len(lines):
                                result_lines.append(lines[i].rstrip("\n"))
                            i += 1
                        
                        patch_idx += 1
                else:
                    patch_idx += 1
            else:
                patch_idx += 1
        
        # 写回文件
        new_content = "\n".join(result_lines)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(new_content)
        
        return {
            "success": True,
            "path": path,
            "changes_applied": len([l for l in patch_lines if l.startswith("+") or l.startswith("-")])
        }
    
    except Exception as e:
        return {"error": str(e)}
