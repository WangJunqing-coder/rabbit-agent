"""
记忆系统 - 跨会话持久化存储
"""
import json
import os
from pathlib import Path
from datetime import datetime
from typing import Optional, Any
from dataclasses import dataclass, field, asdict


@dataclass
class MemoryEntry:
    """记忆条目"""
    id: str
    category: str  # conversation, preference, project, knowledge
    key: str
    value: Any
    created_at: str
    updated_at: str
    metadata: dict = field(default_factory=dict)


class MemoryStore:
    """记忆存储"""
    
    def __init__(self, storage_dir: str = None):
        if storage_dir is None:
            storage_dir = os.path.join(str(Path.home()), ".liteagent", "memory")
        
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        
        # 不同类型的记忆存储文件
        self.files = {
            "conversation": self.storage_dir / "conversations.json",
            "preference": self.storage_dir / "preferences.json",
            "project": self.storage_dir / "projects.json",
            "knowledge": self.storage_dir / "knowledge.json",
        }
        
        # 加载所有记忆
        self.memories: dict[str, list[MemoryEntry]] = {}
        self._load_all()
    
    def _load_all(self):
        """加载所有记忆"""
        for category, filepath in self.files.items():
            if filepath.exists():
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    self.memories[category] = [
                        MemoryEntry(**entry) for entry in data
                    ]
                except (json.JSONDecodeError, TypeError):
                    self.memories[category] = []
            else:
                self.memories[category] = []
    
    def _save(self, category: str):
        """保存指定类别的记忆"""
        filepath = self.files[category]
        entries = self.memories.get(category, [])
        
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(
                [asdict(entry) for entry in entries],
                f,
                ensure_ascii=False,
                indent=2
            )
    
    def add(
        self,
        category: str,
        key: str,
        value: Any,
        metadata: dict = None
    ) -> MemoryEntry:
        """添加记忆"""
        if category not in self.files:
            raise ValueError(f"Unknown category: {category}")
        
        now = datetime.now().isoformat()
        entry_id = f"{category}_{len(self.memories[category])}"
        
        entry = MemoryEntry(
            id=entry_id,
            category=category,
            key=key,
            value=value,
            created_at=now,
            updated_at=now,
            metadata=metadata or {}
        )
        
        self.memories[category].append(entry)
        self._save(category)
        
        return entry
    
    def get(
        self,
        category: str,
        key: str = None,
        limit: int = 10
    ) -> list[MemoryEntry]:
        """获取记忆"""
        entries = self.memories.get(category, [])
        
        if key:
            entries = [e for e in entries if e.key == key]
        
        return entries[-limit:]
    
    def search(
        self,
        query: str,
        categories: list[str] = None
    ) -> list[MemoryEntry]:
        """搜索记忆"""
        results = []
        search_categories = categories or list(self.files.keys())
        
        for category in search_categories:
            for entry in self.memories.get(category, []):
                # 在 key 和 value 中搜索
                value_str = json.dumps(entry.value, ensure_ascii=False) if not isinstance(entry.value, str) else entry.value
                
                if query.lower() in entry.key.lower() or query.lower() in value_str.lower():
                    results.append(entry)
        
        return results
    
    def update(
        self,
        category: str,
        entry_id: str,
        value: Any = None,
        metadata: dict = None
    ) -> Optional[MemoryEntry]:
        """更新记忆"""
        entries = self.memories.get(category, [])
        
        for entry in entries:
            if entry.id == entry_id:
                if value is not None:
                    entry.value = value
                if metadata:
                    entry.metadata.update(metadata)
                entry.updated_at = datetime.now().isoformat()
                self._save(category)
                return entry
        
        return None
    
    def delete(self, category: str, entry_id: str) -> bool:
        """删除记忆"""
        entries = self.memories.get(category, [])
        
        for i, entry in enumerate(entries):
            if entry.id == entry_id:
                entries.pop(i)
                self._save(category)
                return True
        
        return False
    
    def clear(self, category: str = None):
        """清空记忆"""
        if category:
            self.memories[category] = []
            self._save(category)
        else:
            for cat in self.files:
                self.memories[cat] = []
                self._save(cat)
    
    def get_stats(self) -> dict:
        """获取记忆统计"""
        stats = {}
        for category, entries in self.memories.items():
            stats[category] = len(entries)
        stats["total"] = sum(stats.values())
        return stats


class ConversationMemory:
    """对话记忆管理"""
    
    def __init__(self, store: MemoryStore):
        self.store = store
    
    def save_summary(self, session_id: str, summary: str, topics: list[str]):
        """保存对话摘要"""
        self.store.add(
            category="conversation",
            key=session_id,
            value={
                "summary": summary,
                "topics": topics,
                "timestamp": datetime.now().isoformat()
            }
        )
    
    def get_recent(self, limit: int = 5) -> list[dict]:
        """获取最近的对话"""
        entries = self.store.get("conversation", limit=limit)
        return [e.value for e in entries]
    
    def search_topics(self, topic: str) -> list[dict]:
        """按主题搜索对话"""
        entries = self.store.search(topic, categories=["conversation"])
        return [e.value for e in entries]


class ProjectMemory:
    """项目记忆管理"""
    
    def __init__(self, store: MemoryStore):
        self.store = store
    
    def save_project_info(self, project_path: str, info: dict):
        """保存项目信息"""
        self.store.add(
            category="project",
            key=project_path,
            value=info
        )
    
    def get_project_info(self, project_path: str) -> Optional[dict]:
        """获取项目信息"""
        entries = self.store.get("project", key=project_path, limit=1)
        return entries[0].value if entries else None
    
    def save_file_operation(self, file_path: str, operation: str, details: dict):
        """保存文件操作记录"""
        self.store.add(
            category="project",
            key=f"file_op:{file_path}",
            value={
                "file": file_path,
                "operation": operation,
                "details": details,
                "timestamp": datetime.now().isoformat()
            }
        )


class PreferenceMemory:
    """用户偏好记忆管理"""
    
    def __init__(self, store: MemoryStore):
        self.store = store
    
    def save_preference(self, key: str, value: Any):
        """保存用户偏好"""
        # 检查是否已存在
        existing = self.store.get("preference", key=key, limit=1)
        if existing:
            self.store.update("preference", existing[0].id, value=value)
        else:
            self.store.add(
                category="preference",
                key=key,
                value=value
            )
    
    def get_preference(self, key: str, default: Any = None) -> Any:
        """获取用户偏好"""
        entries = self.store.get("preference", key=key, limit=1)
        return entries[0].value if entries else default
    
    def get_all_preferences(self) -> dict:
        """获取所有偏好"""
        entries = self.store.get("preference", limit=100)
        return {e.key: e.value for e in entries}


class KnowledgeMemory:
    """知识记忆管理"""
    
    def __init__(self, store: MemoryStore):
        self.store = store
    
    def save_knowledge(self, topic: str, content: str, source: str = ""):
        """保存知识"""
        self.store.add(
            category="knowledge",
            key=topic,
            value={
                "content": content,
                "source": source,
                "learned_at": datetime.now().isoformat()
            }
        )
    
    def search_knowledge(self, query: str) -> list[dict]:
        """搜索知识"""
        entries = self.store.search(query, categories=["knowledge"])
        return [e.value for e in entries]
    
    def get_by_topic(self, topic: str) -> list[dict]:
        """按主题获取知识"""
        entries = self.store.get("knowledge", key=topic)
        return [e.value for e in entries]


# 全局记忆管理器
class MemoryManager:
    """记忆管理器 - 统一管理所有记忆"""
    
    def __init__(self, storage_dir: str = None):
        self.store = MemoryStore(storage_dir)
        self.conversation = ConversationMemory(self.store)
        self.project = ProjectMemory(self.store)
        self.preference = PreferenceMemory(self.store)
        self.knowledge = KnowledgeMemory(self.store)
    
    def get_context_prompt(self) -> str:
        """获取记忆上下文提示（注入到系统提示中）"""
        parts = []
        
        # 用户偏好
        prefs = self.preference.get_all_preferences()
        if prefs:
            parts.append("## 用户偏好\n")
            for key, value in prefs.items():
                parts.append(f"- {key}: {value}")
        
        # 最近对话
        recent = self.conversation.get_recent(limit=3)
        if recent:
            parts.append("\n## 最近对话摘要\n")
            for conv in recent:
                if isinstance(conv, dict):
                    summary = conv.get("summary", "")
                    if summary:
                        parts.append(f"- {summary}")
        
        # 项目信息
        project_info = self.project.get_project_info(os.getcwd())
        if project_info:
            parts.append("\n## 当前项目信息\n")
            for key, value in project_info.items():
                if isinstance(value, (str, int, float, bool)):
                    parts.append(f"- {key}: {value}")
        
        return "\n".join(parts) if parts else ""
    
    def save_session(self, messages: list, summary: str = None):
        """保存会话"""
        if not summary:
            # 自动生成摘要
            user_messages = [m for m in messages if m.get("role") == "user"]
            if user_messages:
                summary = f"对话包含 {len(user_messages)} 条用户消息"
        
        self.conversation.save_summary(
            session_id=datetime.now().strftime("%Y%m%d_%H%M%S"),
            summary=summary or "",
            topics=[]
        )
