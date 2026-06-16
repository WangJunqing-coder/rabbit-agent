"""
Git 集成工具 - 支持常用 Git 操作
"""
import os
import asyncio
from pathlib import Path
from typing import Optional

from tools.registry import tool


async def run_git_command(command: str, cwd: str = None) -> dict:
    """执行 Git 命令"""
    if cwd is None:
        cwd = os.getcwd()
    
    proc = await asyncio.create_subprocess_shell(
        command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd
    )
    
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
    
    return {
        "stdout": stdout.decode("utf-8", errors="replace").strip(),
        "stderr": stderr.decode("utf-8", errors="replace").strip(),
        "exit_code": proc.returncode
    }


@tool(
    name="git_status",
    description="查看 Git 仓库状态，包括修改、暂存、未跟踪的文件。",
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "仓库路径，默认当前目录",
                "default": "."
            }
        }
    }
)
async def git_status(path: str = ".") -> dict:
    """查看 Git 状态"""
    result = await run_git_command("git status --porcelain", cwd=path)
    
    if result["exit_code"] != 0:
        return {"error": result["stderr"]}
    
    # 解析状态
    files = []
    for line in result["stdout"].splitlines():
        if len(line) >= 3:
            status = line[:2]
            filepath = line[3:]
            
            status_desc = ""
            if status == "M " or status == " M":
                status_desc = "modified"
            elif status == "A ":
                status_desc = "added"
            elif status == "D " or status == " D":
                status_desc = "deleted"
            elif status == "R ":
                status_desc = "renamed"
            elif status == "??":
                status_desc = "untracked"
            elif status == "UU":
                status_desc = "conflict"
            
            files.append({
                "path": filepath,
                "status": status,
                "description": status_desc
            })
    
    # 获取分支信息
    branch_result = await run_git_command("git branch --show-current", cwd=path)
    branch = branch_result["stdout"] if branch_result["exit_code"] == 0 else "unknown"
    
    return {
        "branch": branch,
        "files": files,
        "summary": {
            "modified": len([f for f in files if f["description"] == "modified"]),
            "added": len([f for f in files if f["description"] == "added"]),
            "deleted": len([f for f in files if f["description"] == "deleted"]),
            "untracked": len([f for f in files if f["description"] == "untracked"]),
            "conflicts": len([f for f in files if f["description"] == "conflict"]),
        }
    }


@tool(
    name="git_diff",
    description="查看文件差异。可以查看工作区或暂存区的变更。",
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "仓库路径",
                "default": "."
            },
            "file": {
                "type": "string",
                "description": "指定文件路径（可选）"
            },
            "cached": {
                "type": "boolean",
                "description": "是否查看暂存区差异",
                "default": False
            },
            "stat": {
                "type": "boolean",
                "description": "是否仅显示统计信息",
                "default": False
            }
        }
    }
)
async def git_diff(path: str = ".", file: str = None, cached: bool = False, stat: bool = False) -> dict:
    """查看 Git 差异"""
    cmd = "git diff"
    
    if cached:
        cmd += " --cached"
    
    if stat:
        cmd += " --stat"
    
    if file:
        cmd += f" -- {file}"
    
    result = await run_git_command(cmd, cwd=path)
    
    if result["exit_code"] != 0:
        return {"error": result["stderr"]}
    
    return {
        "diff": result["stdout"],
        "has_changes": bool(result["stdout"])
    }


@tool(
    name="git_log",
    description="查看 Git 提交历史。",
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "仓库路径",
                "default": "."
            },
            "limit": {
                "type": "integer",
                "description": "显示条数",
                "default": 10
            },
            "oneline": {
                "type": "boolean",
                "description": "单行显示",
                "default": True
            }
        }
    }
)
async def git_log(path: str = ".", limit: int = 10, oneline: bool = True) -> dict:
    """查看 Git 日志"""
    cmd = f"git log -{limit}"
    
    if oneline:
        cmd += " --oneline"
    else:
        cmd += " --format=%h|%an|%ae|%ai|%s"
    
    result = await run_git_command(cmd, cwd=path)
    
    if result["exit_code"] != 0:
        return {"error": result["stderr"]}
    
    commits = []
    for line in result["stdout"].splitlines():
        if oneline:
            parts = line.split(" ", 1)
            if len(parts) == 2:
                commits.append({
                    "hash": parts[0],
                    "message": parts[1]
                })
        else:
            parts = line.split("|")
            if len(parts) >= 5:
                commits.append({
                    "hash": parts[0],
                    "author": parts[1],
                    "email": parts[2],
                    "date": parts[3],
                    "message": parts[4]
                })
    
    return {"commits": commits}


@tool(
    name="git_add",
    description="添加文件到暂存区。",
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "仓库路径",
                "default": "."
            },
            "files": {
                "type": "array",
                "items": {"type": "string"},
                "description": "要添加的文件列表，['.'] 表示所有文件"
            }
        },
        "required": ["files"]
    }
)
async def git_add(path: str = ".", files: list[str] = None) -> dict:
    """添加文件到暂存区"""
    if not files:
        return {"error": "No files specified"}
    
    files_str = " ".join(f'"{f}"' for f in files)
    result = await run_git_command(f"git add {files_str}", cwd=path)
    
    if result["exit_code"] != 0:
        return {"error": result["stderr"]}
    
    return {"success": True, "added": files}


@tool(
    name="git_commit",
    description="提交暂存区的变更。",
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "仓库路径",
                "default": "."
            },
            "message": {
                "type": "string",
                "description": "提交信息"
            },
            "add_all": {
                "type": "boolean",
                "description": "是否先添加所有变更",
                "default": False
            }
        },
        "required": ["message"]
    }
)
async def git_commit(path: str = ".", message: str = "", add_all: bool = False) -> dict:
    """提交变更"""
    if add_all:
        await run_git_command("git add -A", cwd=path)
    
    # 转义消息中的特殊字符
    escaped_message = message.replace('"', '\\"')
    result = await run_git_command(f'git commit -m "{escaped_message}"', cwd=path)
    
    if result["exit_code"] != 0:
        return {"error": result["stderr"]}
    
    # 获取提交 hash
    hash_result = await run_git_command("git rev-parse HEAD", cwd=path)
    commit_hash = hash_result["stdout"] if hash_result["exit_code"] == 0 else "unknown"
    
    return {
        "success": True,
        "hash": commit_hash,
        "message": message
    }


@tool(
    name="git_push",
    description="推送到远程仓库。",
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "仓库路径",
                "default": "."
            },
            "remote": {
                "type": "string",
                "description": "远程仓库名",
                "default": "origin"
            },
            "branch": {
                "type": "string",
                "description": "分支名（默认当前分支）"
            }
        }
    }
)
async def git_push(path: str = ".", remote: str = "origin", branch: str = None) -> dict:
    """推送到远程"""
    cmd = f"git push {remote}"
    if branch:
        cmd += f" {branch}"
    
    result = await run_git_command(cmd, cwd=path)
    
    if result["exit_code"] != 0:
        return {"error": result["stderr"], "output": result["stdout"]}
    
    return {"success": True, "output": result["stdout"]}


@tool(
    name="git_pull",
    description="从远程仓库拉取更新。",
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "仓库路径",
                "default": "."
            },
            "remote": {
                "type": "string",
                "description": "远程仓库名",
                "default": "origin"
            },
            "branch": {
                "type": "string",
                "description": "分支名"
            }
        }
    }
)
async def git_pull(path: str = ".", remote: str = "origin", branch: str = None) -> dict:
    """拉取更新"""
    cmd = f"git pull {remote}"
    if branch:
        cmd += f" {branch}"
    
    result = await run_git_command(cmd, cwd=path)
    
    if result["exit_code"] != 0:
        return {"error": result["stderr"], "output": result["stdout"]}
    
    return {"success": True, "output": result["stdout"]}


@tool(
    name="git_branch",
    description="查看或创建分支。",
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "仓库路径",
                "default": "."
            },
            "action": {
                "type": "string",
                "enum": ["list", "create", "switch", "delete"],
                "description": "操作类型",
                "default": "list"
            },
            "name": {
                "type": "string",
                "description": "分支名（create/switch/delete 时必填）"
            }
        }
    }
)
async def git_branch(path: str = ".", action: str = "list", name: str = None) -> dict:
    """分支操作"""
    if action == "list":
        result = await run_git_command("git branch -a", cwd=path)
        if result["exit_code"] != 0:
            return {"error": result["stderr"]}
        
        branches = []
        current = None
        for line in result["stdout"].splitlines():
            line = line.strip()
            if line.startswith("* "):
                current = line[2:]
                branches.append({"name": current, "current": True})
            elif line.startswith("remotes/"):
                branches.append({"name": line, "remote": True})
            else:
                branches.append({"name": line, "current": False})
        
        return {"branches": branches, "current": current}
    
    elif action == "create":
        if not name:
            return {"error": "Branch name required"}
        result = await run_git_command(f"git branch {name}", cwd=path)
    
    elif action == "switch":
        if not name:
            return {"error": "Branch name required"}
        result = await run_git_command(f"git checkout {name}", cwd=path)
    
    elif action == "delete":
        if not name:
            return {"error": "Branch name required"}
        result = await run_git_command(f"git branch -d {name}", cwd=path)
    
    else:
        return {"error": f"Unknown action: {action}"}
    
    if result["exit_code"] != 0:
        return {"error": result["stderr"]}
    
    return {"success": True, "action": action, "branch": name}


@tool(
    name="git_stash",
    description="暂存当前工作区变更。",
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "仓库路径",
                "default": "."
            },
            "action": {
                "type": "string",
                "enum": ["save", "pop", "list", "drop"],
                "description": "操作类型",
                "default": "list"
            },
            "message": {
                "type": "string",
                "description": "暂存消息（save 时可选）"
            }
        }
    }
)
async def git_stash(path: str = ".", action: str = "list", message: str = None) -> dict:
    """Stash 操作"""
    if action == "save":
        cmd = "git stash"
        if message:
            cmd += f' -m "{message}"'
    elif action == "pop":
        cmd = "git stash pop"
    elif action == "list":
        cmd = "git stash list"
    elif action == "drop":
        cmd = "git stash drop"
    else:
        return {"error": f"Unknown action: {action}"}
    
    result = await run_git_command(cmd, cwd=path)
    
    if result["exit_code"] != 0:
        return {"error": result["stderr"]}
    
    return {"success": True, "action": action, "output": result["stdout"]}
