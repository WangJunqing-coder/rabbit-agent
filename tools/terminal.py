"""
终端命令执行工具 - 支持安全过滤
"""
import asyncio
import os
import re
from typing import Optional

from tools.registry import tool
from logger import logger

# ── 危险命令检测 ──────────────────────────────────────────────
# 高危命令模式（匹配任意位置）
DANGEROUS_PATTERNS = [
    # 数据毁灭
    (r'\brm\s+(-[rfR]+\s+)?/', "递归删除根目录/系统文件"),
    (r'\brm\s+(-[rfR]+\s+)?\*', "递归删除通配符文件"),
    (r'\bdd\s+.*of=', "dd 磁盘写入（可能覆盖数据）"),
    (r'\bmkfs\b', "格式化文件系统"),
    (r':\(\)\{.*:\|:.*\}.*:', "fork 炸弹"),
    # 权限/安全
    (r'\bchmod\s+777\b', "设置 777 全开权限"),
    (r'\bchown\s+.*root', "变更为 root 所有者"),
    (r'\b(sudo\s+)?rm\s+.*--no-preserve-root', "删除根目录"),
    # 网络/下载（可能的注入）
    (r'curl\s.*\|\s*(ba)?sh', "远程脚本直接执行"),
    (r'wget\s.*\|\s*(ba)?sh', "远程脚本直接执行"),
    # 系统控制
    (r'\bshutdown\b', "关机"),
    (r'\breboot\b', "重启"),
    (r'\binit\s+[06]', "关机/重启"),
    (r'\bsystemctl\s+(stop|disable)\s+', "停止系统服务"),
]

# 中等风险命令（仅记录日志）
MODERATE_PATTERNS = [
    (r'\bsudo\b', "使用 sudo 提权"),
    (r'\bpip\s+install\b', "安装 Python 包"),
    (r'\bnpm\s+install\b', "安装 Node 包"),
    (r'\bgit\s+push\b', "推送到远程仓库"),
    (r'\bgit\s+reset\s+--hard\b', "硬重置 Git"),
    (r'\bgit\s+clean\s+-[fF]', "Git 清理未跟踪文件"),
]


def check_command_safety(command: str) -> dict:
    """
    检查命令安全性。

    Returns:
        {"safe": bool, "level": "safe"|"warn"|"block", "reason": str}
    """
    # 高危命令 — 阻止
    for pattern, reason in DANGEROUS_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            return {
                "safe": False,
                "level": "block",
                "reason": f"⚠️ 检测到危险操作: {reason}"
            }

    # 中等风险 — 警告但允许
    for pattern, reason in MODERATE_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            logger.warning(f"Suspicious command: {command} ({reason})")
            return {
                "safe": True,
                "level": "warn",
                "reason": f"⚠️ 注意: {reason}"
            }

    return {"safe": True, "level": "safe", "reason": ""}


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
    # 安全检查
    safety = check_command_safety(command)
    if not safety["safe"]:
        logger.warning(f"Blocked dangerous command: {command}")
        return {
            "stdout": "",
            "stderr": safety["reason"],
            "exit_code": -1,
            "blocked": True
        }

    cwd = workdir or os.getcwd()
    
    try:
        # 使用 shell 模式以支持管道、重定向等 shell 特性
        # 注意：LLM 可能生成包含特殊字符的命令，shell=True 存在注入风险
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
