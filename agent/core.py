"""
Agent 核心 - 主循环和上下文管理
"""

import asyncio
import json
import os
import sys
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Optional

from agent.llm import (
    LLMProvider,
    LLMResponse,
    StreamChunk,
    ToolCall,
    create_llm_provider,
)
from config import Config
from context import get_project_context
from memory import MemoryManager
from plugins import get_plugin_manager
from tools.registry import ToolDefinition, registry
from logger import logger

# 基础系统提示词
BASE_SYSTEM_PROMPT = """你是一个强大的 AI 编码助手（Rabbit Agent），类似于 Claude Code 和 Cursor。

## 你的能力

你有以下工具可以使用：
- **terminal**: 执行终端命令（运行代码、安装包、git 操作等）
- **read_file**: 读取文件内容
- **write_file**: 创建或覆盖写入文件
- **edit_file**: 精确编辑文件（查找替换）
- **search_files**: 搜索文件内容（类似 grep）
- **find_files**: 查找文件
- **list_directory**: 列出目录内容
- **batch_edit**: 批量编辑多个文件
- **git_status**: 查看 Git 状态
- **git_diff**: 查看文件差异
- **git_commit**: 提交变更
- **git_push**: 推送到远程
- **git_pull**: 拉取更新
- **git_branch**: 分支操作
- **web_fetch**: 获取网页内容
- **web_search**: 搜索网页
- **delegate_task**: 委派任务给子 Agent

## 工作原则

1. **理解需求**: 先理解用户的完整需求，必要时提问澄清
2. **查看现状**: 使用工具了解项目结构和现有代码
3. **谨慎操作**: 修改文件前先读取确认，避免破坏现有代码
4. **逐步执行**: 复杂任务分步骤完成，每步验证结果
5. **简洁回答**: 用中文回复，技术内容可以中英混用
6. **完成任务**: 确保任务完全完成后再回复用户，不要中途停止

## ⚡ 执行规则（最高优先级，必须严格遵守）

1. **立即行动，禁止预告**：当你决定要做某件事时，必须**立即调用工具**执行。
   - ❌ 错误示范：先输出「现在让我来创建文件...」然后停止
   - ✅ 正确做法：直接调用 write_file / terminal 等工具
2. **禁止只描述意图**：不允许输出「我将要...」「让我来...」「接下来我会...」后就结束回复而不调用工具
3. **一次性完成**：不要做到一半就停下来等待用户确认，除非遇到无法解决的错误
4. **验证结果**：完成操作后确认结果符合预期，如有问题立即修复

## 输出格式

当你需要使用工具时，直接调用相应的函数。
当你完成任务或需要回复用户时，用清晰的中文说明结果。

## 注意事项

- 执行危险命令（rm -rf、格式化等）前要特别小心
- 修改重要文件前建议先备份
- 遇到错误要分析原因并尝试修复
- 不确定时询问用户而不是猜测
- **务必完成整个任务再回复，不要只做一半就停止**
"""


@dataclass
class Message:
    """对话消息"""

    role: str  # system, user, assistant, tool
    content: str
    tool_calls: Optional[list[ToolCall]] = None
    tool_call_id: Optional[str] = None
    name: Optional[str] = None


# 流式输出回调类型
StreamCallback = Callable[[StreamChunk], Awaitable[None]]


class AgentContext:
    """Agent 上下文管理"""

    def __init__(self, config: Config):
        self.config = config
        self.messages: list[Message] = []
        self.working_dir = os.getcwd()

    def add_system_message(self, content: str):
        """添加系统消息"""
        self.messages.append(Message(role="system", content=content))

    def add_user_message(self, content: str):
        """添加用户消息"""
        self.messages.append(Message(role="user", content=content))

    def add_assistant_message(self, content: str, tool_calls: list[ToolCall] = None):
        """添加助手消息"""
        self.messages.append(
            Message(role="assistant", content=content, tool_calls=tool_calls)
        )

    def add_tool_result(self, tool_call_id: str, name: str, content: str):
        """添加工具执行结果"""
        self.messages.append(
            Message(role="tool", content=content, tool_call_id=tool_call_id, name=name)
        )

    def get_messages_for_llm(self) -> list[dict]:
        """获取发送给 LLM 的消息格式"""
        result = []

        for msg in self.messages:
            if msg.role == "system":
                result.append({"role": "system", "content": msg.content})

            elif msg.role == "user":
                result.append({"role": "user", "content": msg.content})

            elif msg.role == "assistant":
                entry = {"role": "assistant", "content": msg.content or ""}
                if msg.tool_calls:
                    entry["tool_calls"] = [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.name,
                                "arguments": json.dumps(
                                    tc.arguments, ensure_ascii=False
                                ),
                            },
                        }
                        for tc in msg.tool_calls
                    ]
                result.append(entry)

            elif msg.role == "tool":
                result.append(
                    {
                        "role": "tool",
                        "content": msg.content,
                        "tool_call_id": msg.tool_call_id,
                    }
                )

        return result

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """粗略估算 token 数（中文 ~1.5 char/token，英文 ~4 char/token）"""
        if not text:
            return 0
        # 简单启发式：中文字符数 / 1.5 + 英文字符数 / 4
        cn_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
        other_chars = len(text) - cn_chars
        return int(cn_chars / 1.5 + other_chars / 4)

    def _message_tokens(self, msg: "Message") -> int:
        """估算单条消息的 token 数"""
        total = self._estimate_tokens(msg.content or "")
        if msg.tool_calls:
            for tc in msg.tool_calls:
                total += self._estimate_tokens(json.dumps(tc.arguments, ensure_ascii=False))
        return total + 4  # role/format overhead

    def trim_messages(self):
        """
        按 token 预算裁剪消息历史。

        策略：
        1. 系统消息永远保留
        2. 最新的用户消息永远保留
        3. 从旧到新裁剪，但保证 tool_call + tool_result 成对保留
        """
        from config import get_context_window
        model = self.config.llm.model
        max_tokens = (
            self.config.llm.context_window
            if self.config.llm.context_window > 0
            else get_context_window(model)
        )
        # 留出 20% 给输出
        token_budget = int(max_tokens * 0.8)

        system_msgs = [m for m in self.messages if m.role == "system"]
        other_msgs = [m for m in self.messages if m.role != "system"]

        # 计算系统消息占用
        system_tokens = sum(self._message_tokens(m) for m in system_msgs)

        # 从最新消息向前保留，直到超出预算
        # 同时保证 tool_call + tool_result 成对
        kept: list[Message] = []
        used_tokens = 0

        # 从后往前遍历
        i = len(other_msgs) - 1
        while i >= 0:
            msg = other_msgs[i]
            msg_tokens = self._message_tokens(msg)

            # 如果是 tool 结果消息，需要和对应的 assistant tool_call 一起保留
            if msg.role == "tool" and i > 0:
                # 向前找对应的 assistant 消息
                prev = other_msgs[i - 1]
                if prev.role == "assistant" and prev.tool_calls:
                    pair_tokens = msg_tokens + self._message_tokens(prev)
                    if system_tokens + used_tokens + pair_tokens <= token_budget:
                        kept.insert(0, msg)
                        kept.insert(0, prev)
                        used_tokens += pair_tokens
                        i -= 2
                        continue

            if system_tokens + used_tokens + msg_tokens <= token_budget:
                kept.insert(0, msg)
                used_tokens += msg_tokens
            else:
                # 超出预算，跳过（但记录跳过了多少条）
                pass
            i -= 1

        self.messages = system_msgs + kept


class Agent:
    """Agent 主类"""

    def __init__(self, config: Config = None):
        self.config = config or Config()
        self.llm: Optional[LLMProvider] = None
        self.context: Optional[AgentContext] = None
        self.memory: Optional[MemoryManager] = None
        self.plugin_manager = None
        self._initialized = False
        self._empty_reply_retries: int = 0  # 空回复重试计数器
        self._incomplete_reply_retries: int = 0  # 只描述意图未执行重试计数器
        self.last_usage: dict = {}  # API 返回的最近一次 token 用量

    async def initialize(self):
        """初始化 Agent"""
        if self._initialized:
            return

        self.llm = create_llm_provider(self.config.llm)
        self.context = AgentContext(self.config)
        self.memory = MemoryManager()
        self.plugin_manager = get_plugin_manager()

        # 构建系统提示
        system_prompt = BASE_SYSTEM_PROMPT

        # 添加项目上下文
        try:
            project_context = get_project_context()
            system_prompt += f"\n\n{project_context}"
        except Exception:
            pass

        # 添加记忆上下文
        try:
            memory_context = self.memory.get_context_prompt()
            if memory_context:
                system_prompt += f"\n\n{memory_context}"
        except Exception:
            pass

        # 添加系统提示
        self.context.add_system_message(system_prompt)

        # 添加工作目录信息
        self.context.add_system_message(f"当前工作目录: {self.context.working_dir}")

        # 初始化子 Agent 管理器
        from tools.sub_agent import init_sub_agent_manager

        init_sub_agent_manager(self)

        self._initialized = True

    async def run(
        self, user_message: str, stream_callback: StreamCallback = None
    ) -> str:
        """
        运行一轮对话

        Args:
            user_message: 用户消息
            stream_callback: 流式输出回调函数

        Returns:
            最终回复内容
        """
        if not self._initialized:
            await self.initialize()

        # 检查是否匹配技能
        skill = self.plugin_manager.match_skill(user_message)
        if skill and skill.system_prompt:
            # 注入技能提示
            self.context.add_system_message(
                f"\n## 当前技能: {skill.name}\n{skill.system_prompt}"
            )

        # 添加用户消息
        self.context.add_user_message(user_message)

        # 裁剪上下文
        self.context.trim_messages()

        # 主循环
        iterations = 0
        final_response = ""
        max_iter = self.config.agent.max_iterations

        while iterations < max_iter:
            iterations += 1

            # 发送迭代状态
            if stream_callback:
                await stream_callback(StreamChunk(
                    event_type="status",
                    content=f"🔄 Iteration {iterations}/{max_iter}",
                    iteration=iterations,
                    max_iterations=max_iter
                ))

            # 调用 LLM
            messages = self.context.get_messages_for_llm()
            schemas = registry.get_schemas()

            # LLM 调用重试逻辑（指数退避）
            response = None
            max_retries = 3
            for retry in range(max_retries):
                try:
                    if stream_callback:
                        # 流式输出
                        response = await self._run_stream(
                            messages, schemas, stream_callback
                        )
                    else:
                        # 非流式输出
                        response = await self.llm.chat(messages, schemas)
                    break  # 成功则跳出重试循环
                except Exception as e:
                    if retry < max_retries - 1:
                        wait_time = 2**retry  # 1s, 2s, 4s
                        if stream_callback:
                            await stream_callback(
                                StreamChunk(
                                    event_type="error",
                                    content=f"⚠️ LLM 调用失败，{wait_time}秒后重试 ({retry + 1}/{max_retries}): {str(e)}"
                                )
                            )
                        await asyncio.sleep(wait_time)
                    else:
                        error_msg = f"LLM 调用失败（已重试{max_retries}次）: {str(e)}"
                        self.context.add_assistant_message(error_msg)
                        return error_msg

            # 检查是否有工具调用
            # 保存 API 返回的 token 用量
            if response.usage:
                self.last_usage = response.usage
            if response.tool_calls:
                # 成功收到工具调用，重置空回复计数器
                self._empty_reply_retries = 0
                # 添加助手消息（带工具调用）
                self.context.add_assistant_message(
                    response.content, response.tool_calls
                )

                # 如果有思考内容（在工具调用之前），发送思考事件
                if response.content and stream_callback:
                    await stream_callback(StreamChunk(
                        event_type="thinking",
                        content=response.content
                    ))

                # 执行所有工具调用
                for tool_call in response.tool_calls:
                    # 通知工具调用（带完整参数）
                    if stream_callback:
                        await stream_callback(StreamChunk(
                            event_type="tool_call",
                            tool_name=tool_call.name,
                            tool_args=tool_call.arguments,
                            content=f"🔧 {tool_call.name}"
                        ))

                    # 执行工具
                    result = await self._execute_tool(tool_call)
                    self.context.add_tool_result(tool_call.id, tool_call.name, result)

                    # 通知工具结果
                    if stream_callback:
                        await stream_callback(StreamChunk(
                            event_type="tool_result",
                            tool_name=tool_call.name,
                            tool_result=result,
                            content=f"✅ {tool_call.name} 完成"
                        ))

                # 继续循环，让 LLM 处理工具结果
                continue

            else:
                # 没有工具调用
                final_response = response.content
                if final_response:
                    # 检测回复是否只是「描述意图」而未实际执行
                    incomplete_retries = getattr(self, "_incomplete_reply_retries", 0)
                    if (
                        self._looks_incomplete(final_response)
                        and incomplete_retries < 3
                    ):
                        self._incomplete_reply_retries = incomplete_retries + 1
                        self.context.add_assistant_message(final_response)
                        if stream_callback:
                            await stream_callback(
                                StreamChunk(
                                    event_type="status",
                                    content=f"⚠️ 检测到只描述了意图，自动继续... ({incomplete_retries + 1}/3)"
                                )
                            )
                        self.context.add_user_message(
                            "你刚才只说了将要做什么，但没有实际调用工具。"
                            "请立即调用 write_file / terminal 等工具执行任务。"
                            "不要描述意图，直接执行。"
                        )
                        continue
                    # 回复看起来是真正完成的，退出循环
                    self._incomplete_reply_retries = 0
                    self.context.add_assistant_message(final_response)
                    break
                else:
                    # 空回复：重试而不是退出
                    empty_retries = getattr(self, "_empty_reply_retries", 0)
                    if empty_retries < 3:
                        self._empty_reply_retries = empty_retries + 1
                        if stream_callback:
                            await stream_callback(
                                StreamChunk(
                                    event_type="status",
                                    content=f"⚠️ LLM 返回空回复，正在重试 ({empty_retries + 1}/3)..."
                                )
                            )
                        # 追加提示消息让 LLM 重新回答
                        self.context.add_user_message(
                            "你的回复为空。请立即调用工具执行任务，不要返回空内容。"
                            "如果需要创建文件，请使用 write_file 工具。"
                        )
                        continue
                    else:
                        # 重试用完，返回提示信息
                        self._empty_reply_retries = 0
                        final_response = "（任务执行中遇到了问题，LLM 返回了空回复。请尝试重新描述您的需求。）"
                        self.context.add_assistant_message(final_response)
                        break

        return final_response

    async def _run_stream(
        self, messages: list[dict], schemas: list[dict], callback: StreamCallback
    ) -> LLMResponse:
        """运行流式输出"""
        full_content = ""
        tool_calls = []
        finish_reason = None
        stream_usage = None

        try:
            async for chunk in self.llm.chat_stream(messages, schemas):
                # 总是调用 callback（用于调试）
                if chunk.content:
                    full_content += chunk.content
                    await callback(chunk)

                # 处理工具调用
                if chunk.tool_calls:
                    tool_calls = chunk.tool_calls
                    # 通知工具调用
                    await callback(chunk)

                # 检查是否完成
                if chunk.is_done:
                    if chunk.usage:
                        stream_usage = chunk.usage
                    finish_reason = chunk.finish_reason
                    break
        except Exception as e:
            # 流式输出出错，尝试回退到非流式模式（带重试）
            logger.error(f"Stream error, falling back to non-stream: {e}")
            for fallback_retry in range(2):
                try:
                    await asyncio.sleep(1 * (fallback_retry + 1))  # 等待 1s, 2s
                    response = await self.llm.chat(messages, schemas)
                    return response
                except Exception as e2:
                    logger.error(f"Fallback attempt {fallback_retry + 1} failed: {e2}")
                    if fallback_retry == 1 and not full_content and not tool_calls:
                        raise e2

        # 如果没有收到完成信号，使用默认值
        if finish_reason is None:
            finish_reason = "stop"

        return LLMResponse(
            content=full_content,
            tool_calls=tool_calls,
            finish_reason=finish_reason,
            usage=stream_usage or {},
        )

    async def _execute_tool(self, tool_call: ToolCall) -> str:
        """执行工具调用（带重试）"""
        tool_name = tool_call.name
        arguments = tool_call.arguments

        last_result = ""
        for attempt in range(self.config.agent.max_tool_retries):
            result = await registry.execute(tool_name, arguments)
            # 检查是否返回了错误
            try:
                result_data = json.loads(result)
                if "error" in result_data:
                    last_result = result
                    if attempt < self.config.agent.max_tool_retries - 1:
                        await asyncio.sleep(0.5 * (attempt + 1))  # 等待 0.5s, 1s
                        continue
            except (json.JSONDecodeError, TypeError):
                pass  # 非 JSON 结果，视为成功
            return result

        return last_result or json.dumps(
            {"error": "Max retries exceeded"}, ensure_ascii=False
        )

    @staticmethod
    def _looks_incomplete(text: str) -> bool:
        """
        检测模型回复是否只是描述了「将要做什么」而没有实际执行。
        这类回复特征：用未来式表达接下来要调用工具的意图，但实际上没有任何工具调用。
        """
        import re

        # 若回复很长（>500字）通常是真正的完成回复，不视为未完成
        if len(text) > 500:
            return False

        # 中文：描述「将要做某事」的模式（更严格匹配）
        cn_future_patterns = [
            r"^(现在|接下来|下面|首先|然后).{0,10}(让我|我来|我将|我会)",
            r"^(让我|让我来).{0,20}(创建|编写|制作|生成|写|做|构建|实现|开始)",
            r"^(我将|我会|我来).{0,20}(创建|编写|制作|生成|写|做|构建|实现|开始)",
            r"^(现在|接下来).{0,20}(创建|编写|制作|生成|构建|实现)",
            r"^(开始|先).{0,10}(创建|编写|制作|生成|写|做|构建|实现)",
            r"^马上(就|开始).{0,20}(创建|编写|制作|生成|写|做)",
            r"^(好的|没问题|可以).{0,5}(现在|接下来|马上).{0,20}(创建|写|做)",
        ]

        # 英文：描述「将要做某事」的模式
        en_future_patterns = [
            r"^let me (now |)?(create|write|make|build|generate|start)",
            r"^i('ll| will| am going to).{0,30}(create|write|make|build|generate)",
            r"^now (let me|i('ll| will)).{0,30}(create|write|make|build)",
        ]

        all_patterns = cn_future_patterns + en_future_patterns
        for pattern in all_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        return False

    async def close(self):
        """清理资源"""
        if self.llm:
            await self.llm.close()

        # 保存会话到记忆
        if self.memory and self.context:
            try:
                self.memory.save_session(
                    [
                        {"role": m.role, "content": m.content}
                        for m in self.context.messages
                    ]
                )
            except Exception:
                pass
