"""
记忆系统工具
"""
import json
from typing import Optional

from tools.registry import tool
from memory.store import get_memory_store, ProjectMemory, UserMemory


@tool(
    name="memory_save",
    description="保存信息到记忆系统。用于记住用户偏好、项目信息、重要决策等跨会话信息。",
    parameters={
        "type": "object",
        "properties": {
            "key": {
                "type": "string",
                "description": "记忆键名（唯一标识）"
            },
            "content": {
                "type": "string",
                "description": "记忆内容"
            },
            "category": {
                "type": "string",
                "description": "分类: user, project, preference, knowledge",
                "default": "general"
            }
        },
        "required": ["key", "content"]
    }
)
async def memory_save(key: str, content: str, category: str = "general") -> dict:
    """保存记忆"""
    store = get_memory_store()
    store.add(key, content, category)
    return {"success": True, "key": key, "category": category}


@tool(
    name="memory_get",
    description="从记忆系统获取信息。用于回忆之前的对话、用户偏好、项目信息等。",
    parameters={
        "type": "object",
        "properties": {
            "key": {
                "type": "string",
                "description": "记忆键名"
            }
        },
        "required": ["key"]
    }
)
async def memory_get(key: str) -> dict:
    """获取记忆"""
    store = get_memory_store()
    content = store.get(key)
    
    if content:
        return {"found": True, "key": key, "content": content}
    else:
        return {"found": False, "key": key, "message": "未找到相关记忆"}


@tool(
    name="memory_search",
    description="搜索记忆。按关键词搜索之前保存的信息。",
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "搜索关键词"
            },
            "category": {
                "type": "string",
                "description": "限定分类（可选）",
                "default": None
            }
        },
        "required": ["query"]
    }
)
async def memory_search(query: str, category: str = None) -> dict:
    """搜索记忆"""
    store = get_memory_store()
    results = store.search(query, category)
    
    return {
        "query": query,
        "total": len(results),
        "results": [
            {
                "key": r.key,
                "content": r.content[:200],
                "category": r.category,
                "timestamp": r.timestamp
            }
            for r in results[:10]
        ]
    }


@tool(
    name="memory_list",
    description="列出所有记忆或指定分类的记忆。",
    parameters={
        "type": "object",
        "properties": {
            "category": {
                "type": "string",
                "description": "分类过滤（可选）",
                "default": None
            }
        }
    }
)
async def memory_list(category: str = None) -> dict:
    """列出记忆"""
    store = get_memory_store()
    entries = store.list_all(category)
    
    return {
        "total": len(entries),
        "entries": [
            {
                "key": e.key,
                "content": e.content[:100],
                "category": e.category,
                "timestamp": e.timestamp
            }
            for e in entries[:20]
        ]
    }


@tool(
    name="memory_delete",
    description="删除指定记忆。",
    parameters={
        "type": "object",
        "properties": {
            "key": {
                "type": "string",
                "description": "要删除的记忆键名"
            }
        },
        "required": ["key"]
    }
)
async def memory_delete(key: str) -> dict:
    """删除记忆"""
    store = get_memory_store()
    deleted = store.delete(key)
    
    if deleted:
        return {"success": True, "key": key}
    else:
        return {"success": False, "key": key, "message": "未找到该记忆"}
