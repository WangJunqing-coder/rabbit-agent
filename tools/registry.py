"""
工具系统 - 注册和管理工具
"""
import json
from typing import Any, Callable, Optional
from dataclasses import dataclass, field


@dataclass
class ToolParameter:
    """工具参数定义"""
    name: str
    type: str
    description: str
    required: bool = True
    enum: Optional[list] = None


@dataclass
class ToolDefinition:
    """工具定义"""
    name: str
    description: str
    parameters: dict  # JSON Schema
    handler: Callable
    
    def to_openai_schema(self) -> dict:
        """转换为 OpenAI function calling 格式"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters
            }
        }


class ToolRegistry:
    """工具注册中心"""
    
    def __init__(self):
        self._tools: dict[str, ToolDefinition] = {}
    
    def register(
        self,
        name: str,
        description: str,
        parameters: dict,
        handler: Callable
    ) -> None:
        """注册工具"""
        self._tools[name] = ToolDefinition(
            name=name,
            description=description,
            parameters=parameters,
            handler=handler
        )
    
    def get(self, name: str) -> Optional[ToolDefinition]:
        """获取工具"""
        return self._tools.get(name)
    
    def list_tools(self) -> list[ToolDefinition]:
        """列出所有工具"""
        return list(self._tools.values())
    
    def get_schemas(self) -> list[dict]:
        """获取所有工具的 schema（用于 LLM）"""
        return [tool.to_openai_schema() for tool in self._tools.values()]
    
    async def execute(self, name: str, arguments: dict) -> str:
        """执行工具"""
        tool = self._tools.get(name)
        if not tool:
            return json.dumps({"error": f"Unknown tool: {name}"})
        
        try:
            result = await tool.handler(**arguments)
            if isinstance(result, dict):
                return json.dumps(result, ensure_ascii=False)
            return str(result)
        except Exception as e:
            return json.dumps({"error": str(e)}, ensure_ascii=False)


# 全局工具注册中心
registry = ToolRegistry()


def tool(
    name: str,
    description: str,
    parameters: dict
):
    """工具装饰器"""
    def decorator(func: Callable):
        registry.register(name, description, parameters, func)
        return func
    return decorator
