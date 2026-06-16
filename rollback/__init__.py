"""
回滚模块 - 支持对话回滚和文件变更恢复
"""
import os
import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field, asdict


@dataclass
class FileChange:
    """文件变更记录"""
    path: str
    operation: str  # create, modify, delete
    old_content: Optional[str] = None
    new_content: Optional[str] = None
    timestamp: str = ""


@dataclass
class Checkpoint:
    """检查点 - 记录一次对话的状态"""
    id: str
    timestamp: str
    description: str
    messages_count: int
    file_changes: list[FileChange] = field(default_factory=list)
    git_commit: Optional[str] = None
    metadata: dict = field(default_factory=dict)


class RollbackManager:
    """回滚管理器"""
    
    def __init__(self, storage_dir: str = None):
        if storage_dir is None:
            storage_dir = os.path.join(str(Path.home()), ".rabbit_agent", "checkpoints")
        
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        
        self.checkpoints: list[Checkpoint] = []
        self.pending_changes: list[FileChange] = []
        
        # 加载检查点
        self._load_checkpoints()
    
    def _load_checkpoints(self):
        """加载检查点"""
        checkpoint_file = self.storage_dir / "checkpoints.json"
        if checkpoint_file.exists():
            try:
                with open(checkpoint_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                
                for cp_data in data:
                    changes = [FileChange(**c) for c in cp_data.get("file_changes", [])]
                    checkpoint = Checkpoint(
                        id=cp_data["id"],
                        timestamp=cp_data["timestamp"],
                        description=cp_data["description"],
                        messages_count=cp_data["messages_count"],
                        file_changes=changes,
                        git_commit=cp_data.get("git_commit"),
                        metadata=cp_data.get("metadata", {})
                    )
                    self.checkpoints.append(checkpoint)
            except Exception as e:
                print(f"Warning: Failed to load checkpoints: {e}")
    
    def _save_checkpoints(self):
        """保存检查点"""
        checkpoint_file = self.storage_dir / "checkpoints.json"
        
        data = []
        for cp in self.checkpoints:
            cp_data = {
                "id": cp.id,
                "timestamp": cp.timestamp,
                "description": cp.description,
                "messages_count": cp.messages_count,
                "file_changes": [asdict(c) for c in cp.file_changes],
                "git_commit": cp.git_commit,
                "metadata": cp.metadata
            }
            data.append(cp_data)
        
        with open(checkpoint_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def record_file_change(self, path: str, operation: str, old_content: str = None, new_content: str = None):
        """记录文件变更"""
        change = FileChange(
            path=os.path.abspath(path),
            operation=operation,
            old_content=old_content,
            new_content=new_content,
            timestamp=datetime.now().isoformat()
        )
        self.pending_changes.append(change)
    
    def create_checkpoint(self, description: str, messages_count: int) -> Checkpoint:
        """创建检查点"""
        checkpoint_id = f"cp_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # 尝试获取当前 Git commit
        git_commit = self._get_current_git_commit()
        
        checkpoint = Checkpoint(
            id=checkpoint_id,
            timestamp=datetime.now().isoformat(),
            description=description,
            messages_count=messages_count,
            file_changes=self.pending_changes.copy(),
            git_commit=git_commit,
            metadata={}
        )
        
        self.checkpoints.append(checkpoint)
        self.pending_changes = []
        
        self._save_checkpoints()
        
        return checkpoint
    
    def _get_current_git_commit(self) -> Optional[str]:
        """获取当前 Git commit hash"""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except:
            pass
        return None
    
    def rollback_last(self) -> Optional[Checkpoint]:
        """回滚到上一个检查点"""
        if len(self.checkpoints) < 2:
            return None
        
        # 获取当前检查点
        current = self.checkpoints[-1]
        target = self.checkpoints[-2]
        
        # 执行回滚
        success = self._apply_rollback(current)
        
        if success:
            # 移除当前检查点
            self.checkpoints.pop()
            self._save_checkpoints()
            return target
        
        return None
    
    def rollback_to(self, checkpoint_id: str) -> Optional[Checkpoint]:
        """回滚到指定检查点"""
        # 找到目标检查点
        target_index = None
        for i, cp in enumerate(self.checkpoints):
            if cp.id == checkpoint_id:
                target_index = i
                break
        
        if target_index is None or target_index == len(self.checkpoints) - 1:
            return None
        
        # 执行回滚（从最新的开始，逐个回滚）
        for i in range(len(self.checkpoints) - 1, target_index, -1):
            current = self.checkpoints[i]
            success = self._apply_rollback(current)
            if not success:
                return None
        
        # 移除已回滚的检查点
        self.checkpoints = self.checkpoints[:target_index + 1]
        self._save_checkpoints()
        
        return self.checkpoints[-1]
    
    def _apply_rollback(self, checkpoint: Checkpoint) -> bool:
        """应用回滚"""
        try:
            # 逆序处理变更
            for change in reversed(checkpoint.file_changes):
                if change.operation == "create":
                    # 创建的文件需要删除
                    try:
                        os.remove(change.path)
                    except FileNotFoundError:
                        pass
                
                elif change.operation == "delete":
                    # 删除的文件需要恢复
                    if change.old_content:
                        Path(change.path).parent.mkdir(parents=True, exist_ok=True)
                        with open(change.path, "w", encoding="utf-8") as f:
                            f.write(change.old_content)
                
                elif change.operation == "modify":
                    # 修改的文件需要恢复原内容
                    if change.old_content:
                        with open(change.path, "w", encoding="utf-8") as f:
                            f.write(change.old_content)
            
            return True
        
        except Exception as e:
            print(f"Rollback failed: {e}")
            return False
    
    def list_checkpoints(self) -> list[Checkpoint]:
        """列出所有检查点"""
        return self.checkpoints.copy()
    
    def get_last_checkpoint(self) -> Optional[Checkpoint]:
        """获取最后一个检查点"""
        return self.checkpoints[-1] if self.checkpoints else None
    
    def get_stats(self) -> dict:
        """获取统计信息"""
        return {
            "total_checkpoints": len(self.checkpoints),
            "pending_changes": len(self.pending_changes),
            "storage_dir": str(self.storage_dir)
        }


# 全局回滚管理器
_rollback_manager: Optional[RollbackManager] = None


def get_rollback_manager() -> RollbackManager:
    """获取回滚管理器"""
    global _rollback_manager
    if _rollback_manager is None:
        _rollback_manager = RollbackManager()
    return _rollback_manager
