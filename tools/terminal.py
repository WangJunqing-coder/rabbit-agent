"""
终端命令执行工具
"""
import asyncio
import os
import subprocess
import sys
from typing import Optional

from tools.registry import tool


@tool(
    name="terminal",
    description="执行终端/shell命令。用于运行代码、安装包、查看系统信息等。返回 stdout、stderr 和退出码。",
    parameters={
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "要执行的 shell 命令"
            },
            "timeout": {
                "type": "integer",
                "description": "超时时间（秒），默认 30",
                "default": 30
            },
            "workdir": {
                "type": "string",
                "description": "工作目录，默认当前目录"
            }
        },
        "required": ["command"]
    }
)
async def terminal(command: str, timeout: int = 30, workdir: str = None) -> dict:
    """执行终端命令"""
    cwd = workdir or os.getcwd()
    
    # Windows 兼容性
    if sys.platform == "win32":
        shell = True
    else:
        shell = True
    
    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd
        )
        
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            proc.kill()
            return {
                "stdout": "",
                "stderr": f"Command timed out after {timeout} seconds",
                "exit_code": -1
            }
        
        return {
            "stdout": stdout.decode("utf-8", errors="replace").strip(),
            "stderr": stderr.decode("utf-8", errors="replace").strip(),
            "exit_code": proc.returncode
        }
        
    except Exception as e:
        return {
            "stdout": "",
            "stderr": str(e),
            "exit_code": -1
        }


@tool(
    name="background_terminal",
    description="在后台执行长时间运行的命令。返回进程 ID，可用 process 工具管理。",
    parameters={
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "要执行的命令"
            },
            "workdir": {
                "type": "string",
                "description": "工作目录"
            }
        },
        "required": ["command"]
    }
)
async def background_terminal(command: str, workdir: str = None) -> dict:
    """后台执行命令"""
    cwd = workdir or os.getcwd()
    
    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd
        )
        
        return {
            "pid": proc.pid,
            "status": "started",
            "message": f"Process started with PID {proc.pid}"
        }
        
    except Exception as e:
        return {
            "error": str(e),
            "status": "failed"
        }
