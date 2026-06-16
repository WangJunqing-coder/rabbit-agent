"""
子 Agent 委派 - 将任务委派给子 Agent 执行
"""
import asyncio
import json
from typing import Optional, Callable
from dataclasses import dataclass

from tools.registry import tool


@dataclass
class SubAgentTask:
    """子 Agent 任务"""
    task_id: str
    description: str
    context: dict
    status: str  # pending, running, completed, failed
    result: Optional[str] = None
    error: Optional[str] = None


class SubAgentManager:
    """子 Agent 管理器"""
    
    def __init__(self, main_agent=None):
        self.main_agent = main_agent
        self.tasks: dict[str, SubAgentTask] = {}
        self.task_counter = 0
    
    async def delegate_task(
        self,
        description: str,
        context: dict = None,
        toolsets: list[str] = None
    ) -> SubAgentTask:
        """委派任务给子 Agent"""
        self.task_counter += 1
        task_id = f"subtask_{self.task_counter}"
        
        task = SubAgentTask(
            task_id=task_id,
            description=description,
            context=context or {},
            status="pending"
        )
        self.tasks[task_id] = task
        
        # 创建子 Agent 执行环境
        task.status = "running"
        
        try:
            result = await self._execute_subtask(task, toolsets)
            task.status = "completed"
            task.result = result
        except Exception as e:
            task.status = "failed"
            task.error = str(e)
        
        return task
    
    async def _execute_subtask(
        self,
        task: SubAgentTask,
        toolsets: list[str] = None
    ) -> str:
        """执行子任务"""
        # 这里简化实现，直接调用主 Agent
        # 实际应该创建独立的子 Agent 实例
        if self.main_agent:
            # 构建子任务提示
            prompt = f"执行以下任务：{task.description}"
            if task.context:
                prompt += f"\n\n上下文信息：\n{json.dumps(task.context, ensure_ascii=False, indent=2)}"
            
            result = await self.main_agent.run(prompt)
            return result
        else:
            raise RuntimeError("No main agent available")
    
    def get_task(self, task_id: str) -> Optional[SubAgentTask]:
        """获取任务状态"""
        return self.tasks.get(task_id)
    
    def list_tasks(self) -> list[dict]:
        """列出所有任务"""
        return [
            {
                "id": task.task_id,
                "description": task.description,
                "status": task.status
            }
            for task in self.tasks.values()
        ]


# 全局子 Agent 管理器
_sub_agent_manager: Optional[SubAgentManager] = None


def init_sub_agent_manager(main_agent=None):
    """初始化子 Agent 管理器"""
    global _sub_agent_manager
    _sub_agent_manager = SubAgentManager(main_agent)


@tool(
    name="delegate_task",
    description="将任务委派给子 Agent 执行。适用于需要独立处理的复杂子任务。",
    parameters={
        "type": "object",
        "properties": {
            "description": {
                "type": "string",
                "description": "任务描述"
            },
            "context": {
                "type": "object",
                "description": "上下文信息（文件路径、变量等）"
            },
            "toolsets": {
                "type": "array",
                "items": {"type": "string"},
                "description": "允许使用的工具集",
                "default": ["terminal", "file_ops", "search"]
            }
        },
        "required": ["description"]
    }
)
async def delegate_task(
    description: str,
    context: dict = None,
    toolsets: list[str] = None
) -> dict:
    """委派任务"""
    if _sub_agent_manager is None:
        return {"error": "Sub-agent manager not initialized"}
    
    task = await _sub_agent_manager.delegate_task(
        description=description,
        context=context,
        toolsets=toolsets
    )
    
    return {
        "task_id": task.task_id,
        "status": task.status,
        "result": task.result,
        "error": task.error
    }


@tool(
    name="list_subtasks",
    description="列出所有子任务状态。",
    parameters={
        "type": "object",
        "properties": {}
    }
)
async def list_subtasks() -> dict:
    """列出子任务"""
    if _sub_agent_manager is None:
        return {"error": "Sub-agent manager not initialized"}
    
    return {"tasks": _sub_agent_manager.list_tasks()}
