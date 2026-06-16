"""
记忆系统 - 跨会话持久化存储
"""
import json
import os
from pathlib import Path
from datetime import datetime
from typing import Optional
from dataclasses import dataclass, field, asdict


@dataclass
class MemoryEntry:
    """记忆条目"""
    key: str
    content: str
    category: str  # user, project, preference, knowledge
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: dict = field(default_factory=dict)


class MemoryStore:
    """记忆存储"""
    
    def __init__(self, storage_dir: str = None):
        self.storage_dir = storage_dir or os.path.join(
            os.path.expanduser("~"), ".liteagent", "memory"
        )
        os.makedirs(self.storage_dir, exist_ok=True)
        
        self.memories_file = os.path.join(self.storage_dir, "memories.json")
        self.memories: dict[str, MemoryEntry] = {}
        self._load()
    
    def _load(self):
        """加载记忆"""
        if os.path.exists(self.memories_file):
            try:
                with open(self.memories_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for key, entry in data.items():
                        self.memories[key] = MemoryEntry(**entry)
            except Exception as e:
                print(f"Warning: Failed to load memories: {e}")
    
    def _save(self):
        """保存记忆"""
        data = {key: asdict(entry) for key, entry in self.memories.items()}
        with open(self.memories_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def add(self, key: str, content: str, category: str = "general", metadata: dict = None):
        """添加记忆"""
        self.memories[key] = MemoryEntry(
            key=key,
            content=content,
            category=category,
            metadata=metadata or {}
        )
        self._save()
    
    def get(self, key: str) -> Optional[str]:
        """获取记忆"""
        entry = self.memories.get(key)
        return entry.content if entry else None
    
    def search(self, query: str, category: str = None) -> list[MemoryEntry]:
        """搜索记忆"""
        results = []
        query_lower = query.lower()
        
        for entry in self.memories.values():
            if category and entry.category != category:
                continue
            
            if (query_lower in entry.key.lower() or 
                query_lower in entry.content.lower()):
                results.append(entry)
        
        return results
    
    def delete(self, key: str) -> bool:
        """删除记忆"""
        if key in self.memories:
            del self.memories[key]
            self._save()
            return True
        return False
    
    def list_all(self, category: str = None) -> list[MemoryEntry]:
        """列出所有记忆"""
        if category:
            return [e for e in self.memories.values() if e.category == category]
        return list(self.memories.values())
    
    def get_summary(self) -> str:
        """获取记忆摘要"""
        categories = {}
        for entry in self.memories.values():
            cat = entry.category
            if cat not in categories:
                categories[cat] = 0
            categories[cat] += 1
        
        lines = ["记忆系统摘要:"]
        for cat, count in categories.items():
            lines.append(f"  - {cat}: {count} 条")
        
        return "\n".join(lines)


class ProjectMemory:
    """项目记忆 - 特定于项目的信息"""
    
    def __init__(self, project_dir: str, store: MemoryStore):
        self.project_dir = project_dir
        self.store = store
        self.prefix = f"project:{project_dir}:"
    
    def save_context(self, key: str, content: str):
        """保存项目上下文"""
        self.store.add(
            f"{self.prefix}{key}",
            content,
            category="project",
            metadata={"project_dir": self.project_dir}
        )
    
    def get_context(self, key: str) -> Optional[str]:
        """获取项目上下文"""
        return self.store.get(f"{self.prefix}{key}")
    
    def save_file_summary(self, file_path: str, summary: str):
        """保存文件摘要"""
        self.save_context(f"file:{file_path}", summary)
    
    def save_decision(self, decision: str, reason: str):
        """保存设计决策"""
        content = f"决策: {decision}\n原因: {reason}"
        self.save_context(f"decision:{datetime.now().isoformat()}", content)
    
    def save_task_history(self, task: str, result: str):
        """保存任务历史"""
        content = f"任务: {task}\n结果: {result}"
        self.save_context(f"task:{datetime.now().isoformat()}", content)


class UserMemory:
    """用户记忆 - 用户偏好和习惯"""
    
    def __init__(self, store: MemoryStore):
        self.store = store
    
    def save_preference(self, key: str, value: str):
        """保存用户偏好"""
        self.store.add(f"pref:{key}", value, category="preference")
    
    def get_preference(self, key: str) -> Optional[str]:
        """获取用户偏好"""
        return self.store.get(f"pref:{key}")
    
    def save_name(self, name: str):
        """保存用户名"""
        self.save_preference("name", name)
    
    def save_language(self, language: str):
        """保存语言偏好"""
        self.save_preference("language", language)
    
    def save_coding_style(self, style: str):
        """保存编码风格"""
        self.save_preference("coding_style", style)


# 全局记忆存储
_memory_store: Optional[MemoryStore] = None


def get_memory_store() -> MemoryStore:
    """获取全局记忆存储"""
    global _memory_store
    if _memory_store is None:
        _memory_store = MemoryStore()
    return _memory_store
