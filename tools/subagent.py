"""
子 Agent 委派系统
"""
import asyncio
import json
import uuid
from typing import Optional
from dataclasses import dataclass

from tools.registry import tool


@dataclass
class SubAgentTask:
    """子 Agent 任务"""
    id: str
    description: str
    status: str  # pending, running, completed, failed
    result: str = ""
    error: str = ""


class SubAgentManager:
    """子 Agent 管理器"""
    
    def __init__(self):
        self.tasks: dict[str, SubAgentTask] = {}
    
    def create_task(self, description: str) -> SubAgentTask:
        """创建任务"""
        task_id = str(uuid.uuid4())[:8]
        task = SubAgentTask(
            id=task_id,
            description=description,
            status="pending"
        )
        self.tasks[task_id] = task
        return task
    
    def get_task(self, task_id: str) -> Optional[SubAgentTask]:
        """获取任务"""
        return self.tasks.get(task_id)
    
    def list_tasks(self) -> list[SubAgentTask]:
        """列出所有任务"""
        return list(self.tasks.values())


# 全局子 Agent 管理器
_sub_agent_manager = SubAgentManager()


@tool(
    name="delegate_task",
    description="将任务委派给子 Agent 执行。适用于需要独立执行的子任务，如并行测试、独立模块开发等。",
    parameters={
        "type": "object",
        "properties": {
            "task": {
                "type": "string",
                "description": "任务描述"
            },
            "context": {
                "type": "string",
                "description": "任务上下文信息",
                "default": ""
            }
        },
        "required": ["task"]
    }
)
async def delegate_task(task: str, context: str = "") -> dict:
    """委派任务"""
    # 这里只是创建任务记录，实际执行需要集成到 Agent 主循环
    sub_task = _sub_agent_manager.create_task(task)
    
    return {
        "task_id": sub_task.id,
        "description": task,
        "context": context,
        "status": "created",
        "message": f"任务已创建，ID: {sub_task.id}。可以通过子 Agent 执行。"
    }


@tool(
    name="subagent_status",
    description="查看子 Agent 任务状态。",
    parameters={
        "type": "object",
        "properties": {
            "task_id": {
                "type": "string",
                "description": "任务 ID（可选，不指定则列出所有）",
                "default": None
            }
        }
    }
)
async def subagent_status(task_id: str = None) -> dict:
    """查看任务状态"""
    if task_id:
        task = _sub_agent_manager.get_task(task_id)
        if task:
            return {
                "id": task.id,
                "description": task.description,
                "status": task.status,
                "result": task.result,
                "error": task.error
            }
        else:
            return {"error": f"Task not found: {task_id}"}
    else:
        tasks = _sub_agent_manager.list_tasks()
        return {
            "total": len(tasks),
            "tasks": [
                {
                    "id": t.id,
                    "description": t.description[:50],
                    "status": t.status
                }
                for t in tasks
            ]
        }


@tool(
    name="parallel_tasks",
    description="并行执行多个任务。适用于同时处理多个独立工作。",
    parameters={
        "type": "object",
        "properties": {
            "tasks": {
                "type": "array",
                "description": "任务列表",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "任务名称"},
                        "command": {"type": "string", "description": "执行命令"}
                    },
                    "required": ["name", "command"]
                }
            }
        },
        "required": ["tasks"]
    }
)
async def parallel_tasks(tasks: list) -> dict:
    """并行执行任务"""
    results = []
    
    async def run_task(task_info):
        name = task_info["name"]
        command = task_info["command"]
        
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
            
            return {
                "name": name,
                "status": "success" if proc.returncode == 0 else "failed",
                "stdout": stdout.decode()[:1000],
                "stderr": stderr.decode()[:500] if stderr else "",
                "exit_code": proc.returncode
            }
        except asyncio.TimeoutError:
            return {
                "name": name,
                "status": "timeout",
                "error": "Task timed out after 120 seconds"
            }
        except Exception as e:
            return {
                "name": name,
                "status": "error",
                "error": str(e)
            }
    
    # 并行执行所有任务
    results = await asyncio.gather(*[run_task(t) for t in tasks])
    
    return {
        "total": len(tasks),
        "results": list(results)
    }
