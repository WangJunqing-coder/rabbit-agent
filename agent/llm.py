"""
LLM 接口层 - 支持多种后端和流式输出
"""
import logging
import json
from typing import Any, Optional, AsyncIterator
from dataclasses import dataclass

import httpx

logger = logging.getLogger("rabbit_agent.llm")

from config import LLMConfig


@dataclass
class ToolCall:
    """工具调用"""
    id: str
    name: str
    arguments: dict


@dataclass
class LLMResponse:
    """LLM 响应"""
    content: str
    tool_calls: list[ToolCall]
    finish_reason: str
    usage: dict


@dataclass
class StreamChunk:
    """流式响应块"""
    content: str = ""
    tool_calls: list[ToolCall] = None
    finish_reason: str = None
    is_done: bool = False
    usage: dict = None
    # 流程展示字段
    event_type: str = ""  # thinking/tool_call/tool_result/status/error
    tool_name: str = ""   # 工具名称（用于 tool_result）
    tool_args: dict = None  # 工具参数（用于 tool_call）
    tool_result: str = ""  # 工具执行结果
    iteration: int = 0    # 当前迭代轮次
    max_iterations: int = 0  # 最大迭代次数


class LLMProvider:
    """LLM 提供者基类"""
    
    def __init__(self, config: LLMConfig):
        self.config = config
        self.client = httpx.AsyncClient(
            base_url=config.api_base,
            timeout=config.timeout
        )
    
    async def chat(
        self,
        messages: list[dict],
        tools: Optional[list[dict]] = None
    ) -> LLMResponse:
        raise NotImplementedError
    
    async def chat_stream(
        self,
        messages: list[dict],
        tools: Optional[list[dict]] = None
    ) -> AsyncIterator[StreamChunk]:
        raise NotImplementedError
    
    async def close(self):
        await self.client.aclose()


def _repair_tool_arguments(args_raw) -> dict:
    """
    修复 LLM 返回的不完整/截断的工具调用参数 JSON。

    处理场景：
    1. JSON 字符串被截断（末尾缺少 }）
    2. 无法解析的 JSON（用正则提取已知字段）
    """
    if not isinstance(args_raw, str):
        return args_raw if isinstance(args_raw, dict) else {}

    args_str = args_raw.strip()

    # 尝试直接解析
    try:
        return json.loads(args_str)
    except json.JSONDecodeError:
        pass

    # 尝试修复截断：补全末尾
    if not args_str.endswith("}"):
        fixed = args_str + '"}'
        try:
            return json.loads(fixed)
        except json.JSONDecodeError:
            pass

    # 正则提取已知字段（兜底方案）
    import re
    arguments = {}
    path_match = re.search(r'"path"\s*:\s*"([^"]*)"', args_str)
    content_match = re.search(r'"content"\s*:\s*"(.*)', args_str, re.DOTALL)

    if path_match:
        arguments["path"] = path_match.group(1)
    if content_match:
        content = content_match.group(1)
        if not content.endswith('"'):
            content += '"'
        try:
            arguments["content"] = json.loads('"' + content + '"')
        except (json.JSONDecodeError, ValueError):
            arguments["content"] = content.rstrip('"')

    return arguments


class OpenAICompatibleProvider(LLMProvider):
    """OpenAI 兼容接口（支持 Ollama, DeepSeek, OpenAI 等）"""
    
    def _build_payload(
        self,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
        stream: bool = False
    ) -> dict:
        """构建请求 payload"""
        payload = {
            "model": self.config.model,
            "messages": messages,
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
            "stream": stream
        }
        if stream:
            payload["stream_options"] = {"include_usage": True}
        
        
        # Ollama 需要 options 参数
        if "ollama" in self.config.api_base or "localhost:11434" in self.config.api_base:
            payload["options"] = {
                "num_predict": self.config.max_tokens,
                "temperature": self.config.temperature
            }
        
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        
        return payload
    
    def _get_headers(self) -> dict:
        """获取请求头"""
        headers = {"Content-Type": "application/json"}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        return headers
    
    async def chat(
        self,
        messages: list[dict],
        tools: Optional[list[dict]] = None
    ) -> LLMResponse:
        """非流式聊天"""
        payload = self._build_payload(messages, tools, stream=False)
        
        response = await self.client.post(
            "/chat/completions",
            json=payload,
            headers=self._get_headers()
        )
        response.raise_for_status()
        data = response.json()
        
        choice = data["choices"][0]
        message = choice["message"]
        
        # 解析工具调用
        tool_calls = []
        if "tool_calls" in message and message["tool_calls"]:
            for tc in message["tool_calls"]:
                try:
                    arguments = _repair_tool_arguments(tc["function"]["arguments"])
                except Exception:
                    arguments = {}
                
                tool_calls.append(ToolCall(
                    id=tc.get("id", f"call_{len(tool_calls)}"),
                    name=tc["function"]["name"],
                    arguments=arguments
                ))
        
        return LLMResponse(
            content=message.get("content", ""),
            tool_calls=tool_calls,
            finish_reason=choice.get("finish_reason", "stop"),
            usage=data.get("usage", {})
        )
    
    async def chat_stream(
        self,
        messages: list[dict],
        tools: Optional[list[dict]] = None
    ) -> AsyncIterator[StreamChunk]:
        """流式聊天"""
        payload = self._build_payload(messages, tools, stream=True)
        
        async with self.client.stream(
            "POST",
            "/chat/completions",
            json=payload,
            headers=self._get_headers()
        ) as response:
            response.raise_for_status()
            
            tool_call_buffers = {}
            full_content = ""
            stream_usage = None
            
            async for line in response.aiter_lines():
                if not line.startswith("data: "):
                    continue
                
                data_str = line[6:].strip()
                if data_str == "[DONE]":
                    yield StreamChunk(is_done=True, usage=stream_usage)
                    break
                
                try:
                    data = json.loads(data_str)
                except json.JSONDecodeError:
                    continue
                
                # 捕获 API 返回的 token 用量
                if "usage" in data and data["usage"]:
                    stream_usage = data["usage"]
                
                choice = data.get("choices", [{}])[0]
                delta = choice.get("delta", {})
                finish_reason = choice.get("finish_reason")
                
                content = delta.get("content", "")
                if content:
                    full_content += content
                
                tool_calls = []
                if "tool_calls" in delta:
                    for tc in delta["tool_calls"]:
                        idx = tc.get("index", 0)
                        if idx not in tool_call_buffers:
                            tool_call_buffers[idx] = {
                                "id": tc.get("id", ""),
                                "name": "",
                                "arguments": ""
                            }
                        
                        if "id" in tc:
                            tool_call_buffers[idx]["id"] = tc["id"]
                        if "function" in tc:
                            if "name" in tc["function"]:
                                tool_call_buffers[idx]["name"] = tc["function"]["name"]
                            if "arguments" in tc["function"]:
                                tool_call_buffers[idx]["arguments"] += tc["function"]["arguments"]
                
                if finish_reason == "tool_calls" or (finish_reason == "stop" and tool_call_buffers):
                    for idx, buf in tool_call_buffers.items():
                        if buf["name"] and buf["arguments"]:
                            try:
                                arguments = _repair_tool_arguments(buf["arguments"])
                            except Exception:
                                arguments = {}
                            
                            tool_calls.append(ToolCall(
                                id=buf["id"] or f"call_{idx}",
                                name=buf["name"],
                                arguments=arguments
                            ))
                
                yield StreamChunk(
                    content=content,
                    tool_calls=tool_calls if tool_calls else None,
                    finish_reason=finish_reason,
                    is_done=finish_reason is not None
                )

class AnthropicProvider(LLMProvider):
    """Anthropic Claude 接口"""
    
    async def chat(
        self,
        messages: list[dict],
        tools: Optional[list[dict]] = None
    ) -> LLMResponse:
        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.config.api_key,
            "anthropic-version": "2023-06-01"
        }
        
        # 分离 system 消息
        system_msg = ""
        chat_messages = []
        for msg in messages:
            if msg["role"] == "system":
                system_msg = msg["content"]
            else:
                chat_messages.append(msg)
        
        payload = {
            "model": self.config.model,
            "messages": chat_messages,
            "max_tokens": self.config.max_tokens,
            "temperature": self.config.temperature
        }
        
        if system_msg:
            payload["system"] = system_msg
        
        if tools:
            payload["tools"] = [self._convert_tool(t) for t in tools]
        
        response = await self.client.post(
            "/messages",
            json=payload,
            headers=headers
        )
        response.raise_for_status()
        data = response.json()
        
        # 解析响应
        content = ""
        tool_calls = []
        
        for block in data.get("content", []):
            if block["type"] == "text":
                content += block["text"]
            elif block["type"] == "tool_use":
                tool_calls.append(ToolCall(
                    id=block["id"],
                    name=block["name"],
                    arguments=block["input"]
                ))
        
        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            finish_reason=data.get("stop_reason", "end_turn"),
            usage=data.get("usage", {})
        )
    
    async def chat_stream(
        self,
        messages: list[dict],
        tools: Optional[list[dict]] = None
    ) -> AsyncIterator[StreamChunk]:
        """Anthropic 流式接口"""
        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.config.api_key,
            "anthropic-version": "2023-06-01"
        }
        
        system_msg = ""
        chat_messages = []
        for msg in messages:
            if msg["role"] == "system":
                system_msg = msg["content"]
            else:
                chat_messages.append(msg)
        
        payload = {
            "model": self.config.model,
            "messages": chat_messages,
            "max_tokens": self.config.max_tokens,
            "temperature": self.config.temperature,
            "stream": True
        }
        
        if system_msg:
            payload["system"] = system_msg
        
        if tools:
            payload["tools"] = [self._convert_tool(t) for t in tools]
        
        async with self.client.stream(
            "POST",
            "/messages",
            json=payload,
            headers=headers
        ) as response:
            response.raise_for_status()
            
            tool_calls = []
            
            async for line in response.aiter_lines():
                if not line.startswith("data: "):
                    continue
                
                data_str = line[6:].strip()
                try:
                    data = json.loads(data_str)
                    event_type = data.get("type")
                    
                    if event_type == "content_block_delta":
                        delta = data.get("delta", {})
                        if delta.get("type") == "text_delta":
                            yield StreamChunk(content=delta.get("text", ""))
                    
                    elif event_type == "content_block_start":
                        block = data.get("content_block", {})
                        if block.get("type") == "tool_use":
                            tool_calls.append(ToolCall(
                                id=block.get("id", ""),
                                name=block.get("name", ""),
                                arguments={}
                            ))
                    
                    elif event_type == "message_stop":
                        yield StreamChunk(
                            tool_calls=tool_calls if tool_calls else None,
                            finish_reason="stop",
                            is_done=True
                        )
                        
                except json.JSONDecodeError:
                    continue
    
    def _convert_tool(self, tool: dict) -> dict:
        """转换工具格式到 Anthropic 格式"""
        return {
            "name": tool["function"]["name"],
            "description": tool["function"]["description"],
            "input_schema": tool["function"]["parameters"]
        }


def create_llm_provider(config: LLMConfig) -> LLMProvider:
    """创建 LLM 提供者"""
    if config.provider == "anthropic":
        return AnthropicProvider(config)
    else:
        return OpenAICompatibleProvider(config)
