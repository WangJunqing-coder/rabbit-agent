"""
子 Agent 委派 - 真正的独立子 Agent 实现

子 Agent 拥有独立的上下文和 LLM 调用，不会污染主 Agent 的对话历史。
"""
import asyncio
import json
import uuid
from typing import Optional
from dataclasses import dataclass

from tools.registry import tool
from logger import logger


@dataclass
class SubAgentTask:
    """子 Agent 任务"""
    task_id: str
    description: str
    context: str
    status: str  # pending, running, completed, failed
    result: str = ""
    error: str = ""


class SubAgentManager:
    """
    子 Agent 管理器

    每个子任务使用独立的 Agent 实例运行，拥有自己的上下文窗口，
    不会污染主 Agent 的对话历史。
    """

    def __init__(self, main_agent=None):
        self.main_agent = main_agent
        self.tasks: dict[str, SubAgentTask] = {}
        self.task_counter = 0

    async def delegate_task(
        self,
        description: str,
        context: str = "",
        toolsets: list[str] = None
    ) -> SubAgentTask:
        """委派任务给独立子 Agent"""
        self.task_counter += 1
        task_id = f"sub_{self.task_counter}"

        task = SubAgentTask(
            task_id=task_id,
            description=description,
            context=context,
            status="pending"
        )
        self.tasks[task_id] = task

        # 在独立上下文中执行
        task.status = "running"
        try:
            result = await self._run_independent_agent(task, toolsets)
            task.status = "completed"
            task.result = result
        except Exception as e:
            task.status = "failed"
            task.error = str(e)
            logger.error(f"Sub-agent task {task_id} failed: {e}")

        return task

    async def _run_independent_agent(
        self,
        task: SubAgentTask,
        toolsets: list[str] = None
    ) -> str:
        """
        创建独立 Agent 实例执行子任务。

        关键设计：
        - 使用主 Agent 的 config（LLM 配置）
        - 创建全新的 AgentContext（独立上下文）
        - 只注册允许的工具子集（如果指定了 toolsets）
        """
        from agent.core import Agent, AgentContext, BASE_SYSTEM_PROMPT
        from tools.registry import registry

        # 创建独立 Agent（复用主 Agent 的配置）
        sub_agent = Agent(self.main_agent.config)

        # 手动初始化（不调用 initialize 避免重复注册子 Agent 管理器）
        from agent.llm import create_llm_provider
        sub_agent.llm = create_llm_provider(sub_agent.config)
        sub_agent.context = AgentContext(sub_agent.config)

        # 独立的系统提示（精简版，不注入主 Agent 的记忆）
        sub_prompt = (
            BASE_SYSTEM_PROMPT
            + "\n\n你是一个子 Agent，正在执行一个独立的子任务。"
            "请专注于完成这个任务，结果将返回给主 Agent。"
            "请直接给出任务结果，不需要额外的寒暄。"
        )
        sub_agent.context.add_system_message(sub_prompt)

        # 构建任务消息
        task_msg = f"## 子任务\n\n{task.description}"
        if task.context:
            task_msg += f"\n\n## 上下文信息\n\n{task.context}"
        sub_agent.context.add_user_message(task_msg)

        # 获取工具 schema（可选：过滤工具集）
        if toolsets:
            allowed = set(toolsets)
            schemas = [
                s for s in registry.get_schemas()
                if s["function"]["name"] in allowed
            ]
        else:
            schemas = registry.get_schemas()

        # 运行子 Agent（最多 20 轮迭代）
        max_iterations = 20
        for iteration in range(max_iterations):
            messages = sub_agent.context.get_messages_for_llm()

            try:
                response = await sub_agent.llm.chat(messages, schemas)
            except Exception as e:
                logger.error(f"Sub-agent LLM call failed: {e}")
                raise

            if response.usage:
                sub_agent.last_usage = response.usage

            # 检查工具调用
            if response.tool_calls:
                sub_agent.context.add_assistant_message(
                    response.content, response.tool_calls
                )
                for tc in response.tool_calls:
                    result = await registry.execute(tc.name, tc.arguments)
                    sub_agent.context.add_tool_result(tc.id, tc.name, result)
                continue

            # 没有工具调用，返回结果
            final = response.content or ""
            sub_agent.context.add_assistant_message(final)

            # 清理子 Agent 资源
            await sub_agent.llm.close()
            return final

        # 超过最大迭代
        await sub_agent.llm.close()
        return sub_agent.context.messages[-1].content if sub_agent.context.messages else "子任务超过最大迭代次数"

    def get_task(self, task_id: str) -> Optional[SubAgentTask]:
        """获取任务状态"""
        return self.tasks.get(task_id)

    def list_tasks(self) -> list[dict]:
        """列出所有任务"""
        return [
            {
                "id": task.task_id,
                "description": task.description[:50],
                "status": task.status,
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
    description="将任务委派给独立子 Agent 执行。子 Agent 拥有独立上下文，不会污染主对话。适用于需要独立处理的复杂子任务。",
    parameters={
        "type": "object",
        "properties": {
            "description": {
                "type": "string",
                "description": "任务描述"
            },
            "context": {
                "type": "string",
                "description": "上下文信息（文件路径、变量、约束等）",
                "default": ""
            },
            "toolsets": {
                "type": "array",
                "items": {"type": "string"},
                "description": "允许使用的工具列表（可选，默认全部）"
            }
        },
        "required": ["description"]
    }
)
async def delegate_task(
    description: str,
    context: str = "",
    toolsets: list[str] = None
) -> dict:
    """委派任务给子 Agent"""
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
