"""
记忆系统工具 — 基于统一的 MemoryManager
"""
from typing import Optional

from tools.registry import tool
from memory import MemoryManager

# 统一使用 MemoryManager（来自 memory/__init__.py），
# 避免 memory/store.py 的双重实现冲突。
_manager: Optional[MemoryManager] = None


def _get_manager() -> MemoryManager:
    global _manager
    if _manager is None:
        _manager = MemoryManager()
    return _manager


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
                "description": "分类: conversation, preference, project, knowledge",
                "default": "knowledge"
            }
        },
        "required": ["key", "content"]
    }
)
async def memory_save(key: str, content: str, category: str = "knowledge") -> dict:
    """保存记忆"""
    mgr = _get_manager()
    try:
        mgr.store.add(category=category, key=key, value=content)
        return {"success": True, "key": key, "category": category}
    except ValueError as e:
        return {"success": False, "key": key, "error": str(e)}


@tool(
    name="memory_get",
    description="从记忆系统获取信息。用于回忆之前的对话、用户偏好、项目信息等。",
    parameters={
        "type": "object",
        "properties": {
            "key": {
                "type": "string",
                "description": "记忆键名"
            },
            "category": {
                "type": "string",
                "description": "可选：限定分类",
                "default": None
            }
        },
        "required": ["key"]
    }
)
async def memory_get(key: str, category: str = None) -> dict:
    """获取记忆"""
    mgr = _get_manager()
    # 搜索所有类别
    results = mgr.store.search(key)
    if results:
        entry = results[0]
        return {
            "found": True,
            "key": entry.key,
            "content": entry.value,
            "category": entry.category
        }
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
    mgr = _get_manager()
    categories = [category] if category else None
    results = mgr.store.search(query, categories=categories)

    return {
        "query": query,
        "total": len(results),
        "results": [
            {
                "key": r.key,
                "content": str(r.value)[:200],
                "category": r.category,
                "timestamp": r.updated_at
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
    mgr = _get_manager()
    stats = mgr.store.get_stats()
    
    if category:
        entries = mgr.store.get(category, limit=100)
    else:
        entries = []
        for cat in ["conversation", "preference", "project", "knowledge"]:
            entries.extend(mgr.store.get(cat, limit=25))

    return {
        "total": len(entries),
        "stats": stats,
        "entries": [
            {
                "key": e.key,
                "content": str(e.value)[:100],
                "category": e.category,
                "timestamp": e.updated_at
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
            },
            "category": {
                "type": "string",
                "description": "记忆所属分类",
                "default": None
            }
        },
        "required": ["key"]
    }
)
async def memory_delete(key: str, category: str = None) -> dict:
    """删除记忆"""
    mgr = _get_manager()
    # 搜索匹配的记忆
    results = mgr.store.search(key)
    for entry in results:
        if entry.key == key:
            mgr.store.delete(entry.category, entry.id)
            return {"success": True, "key": key}
    return {"success": False, "key": key, "message": "未找到该记忆"}
