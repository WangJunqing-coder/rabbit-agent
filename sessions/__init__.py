"""
会话管理模块 - 支持多会话切换和管理
"""
import json
import os
import uuid
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field, asdict

logger = logging.getLogger("rabbit_agent.sessions")


@dataclass
class Session:
    """会话信息"""
    id: str
    title: str
    created_at: str
    updated_at: str
    messages: list = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


class SessionManager:
    """会话管理器"""
    
    def __init__(self, storage_dir: str = None):
        if storage_dir is None:
            storage_dir = os.path.join(str(Path.home()), ".rabbit_agent", "sessions")
        
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        
        self.sessions: dict[str, Session] = {}
        self.current_session_id: Optional[str] = None
        
        # 加载所有会话
        self._load_sessions()
    
    def _load_sessions(self):
        """加载所有会话"""
        for file_path in self.storage_dir.glob("*.json"):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                
                session = Session(
                    id=data["id"],
                    title=data["title"],
                    created_at=data["created_at"],
                    updated_at=data["updated_at"],
                    messages=data.get("messages", []),
                    metadata=data.get("metadata", {})
                )
                self.sessions[session.id] = session
            except Exception as e:
                logger.warning(f"Failed to load session {file_path}: {e}")
    
    def _save_session(self, session: Session):
        """保存会话到文件"""
        file_path = self.storage_dir / f"{session.id}.json"
        
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(asdict(session), f, ensure_ascii=False, indent=2)
    
    def _delete_session_file(self, session_id: str):
        """删除会话文件"""
        file_path = self.storage_dir / f"{session_id}.json"
        if file_path.exists():
            file_path.unlink()
    
    def create_session(self, title: str = None) -> Session:
        """创建新会话"""
        session_id = str(uuid.uuid4())[:8]
        now = datetime.now().isoformat()
        
        if not title:
            title = f"会话 {len(self.sessions) + 1}"
        
        session = Session(
            id=session_id,
            title=title,
            created_at=now,
            updated_at=now,
            messages=[],
            metadata={}
        )
        
        self.sessions[session_id] = session
        self._save_session(session)
        
        self.current_session_id = session_id
        
        return session
    
    def get_session(self, session_id: str) -> Optional[Session]:
        """获取会话"""
        return self.sessions.get(session_id)
    
    def get_current_session(self) -> Optional[Session]:
        """获取当前会话"""
        if self.current_session_id:
            return self.sessions.get(self.current_session_id)
        return None
    
    def switch_session(self, session_id: str) -> Optional[Session]:
        """切换会话"""
        if session_id in self.sessions:
            self.current_session_id = session_id
            return self.sessions[session_id]
        return None
    
    def update_session(self, session_id: str, title: str = None, messages: list = None):
        """更新会话"""
        session = self.sessions.get(session_id)
        if not session:
            return
        
        if title is not None:
            session.title = title
        
        if messages is not None:
            session.messages = messages
        
        session.updated_at = datetime.now().isoformat()
        self._save_session(session)
    
    def delete_session(self, session_id: str) -> bool:
        """删除会话"""
        if session_id not in self.sessions:
            return False
        
        del self.sessions[session_id]
        self._delete_session_file(session_id)
        
        # 如果删除的是当前会话，切换到最新的会话
        if self.current_session_id == session_id:
            if self.sessions:
                self.current_session_id = max(
                    self.sessions.keys(),
                    key=lambda sid: self.sessions[sid].updated_at
                )
            else:
                self.current_session_id = None
        
        return True
    
    def list_sessions(self, sort_by: str = "updated_at") -> list[Session]:
        """列出所有会话"""
        sessions = list(self.sessions.values())
        
        if sort_by == "updated_at":
            sessions.sort(key=lambda s: s.updated_at, reverse=True)
        elif sort_by == "created_at":
            sessions.sort(key=lambda s: s.created_at, reverse=True)
        elif sort_by == "title":
            sessions.sort(key=lambda s: s.title)
        
        return sessions
    
    def get_session_messages(self, session_id: str) -> list:
        """获取会话消息"""
        session = self.sessions.get(session_id)
        return session.messages if session else []
    
    def add_message(self, session_id: str, role: str, content: str):
        """添加消息到会话"""
        session = self.sessions.get(session_id)
        if not session:
            return
        
        session.messages.append({
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat()
        })
        
        session.updated_at = datetime.now().isoformat()
        
        # 自动更新标题（使用第一条用户消息）
        if role == "user" and len(session.messages) == 1:
            # 截取前30个字符作为标题
            title = content[:30] + "..." if len(content) > 30 else content
            session.title = title
        
        self._save_session(session)
    
    def get_stats(self) -> dict:
        """获取统计信息"""
        return {
            "total_sessions": len(self.sessions),
            "current_session": self.current_session_id,
            "storage_dir": str(self.storage_dir)
        }


# 全局会话管理器
_session_manager: Optional[SessionManager] = None


def get_session_manager() -> SessionManager:
    """获取会话管理器"""
    global _session_manager
    if _session_manager is None:
        _session_manager = SessionManager()
    return _session_manager
