"""
Rabbit Agent 配置管理
"""
import os
from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path

import yaml


@dataclass
class LLMConfig:
    """LLM 配置"""
    provider: str = "ollama"
    model: str = "gemma4:latest"
    api_base: str = "http://localhost:11434/v1"
    api_key: str = ""
    temperature: float = 0.7
    max_tokens: int = 4096
    timeout: int = 120
    context_window: int = 0  # 0 means auto-detect


@dataclass
class AgentConfig:
    """Agent 配置"""
    max_iterations: int = 200
    max_tool_retries: int = 3
    tool_timeout: int = 60
    max_context_messages: int = 50
    terminal_timeout: int = 30
    max_file_size: int = 1_048_576  # 1MB


@dataclass
class UIConfig:
    """界面配置"""
    language: str = "zh"
    show_token_usage: bool = True
    color_theme: str = "default"


@dataclass
class Config:
    """主配置"""
    llm: LLMConfig = field(default_factory=LLMConfig)
    agent: AgentConfig = field(default_factory=AgentConfig)
    ui: UIConfig = field(default_factory=UIConfig)
    
    @classmethod
    def load(cls, config_path: str = None) -> "Config":
        """
        加载配置文件
        
        优先级: 命令行参数 > 环境变量 > 配置文件 > 默认值
        """
        config = cls()
        
        # 1. 尝试加载配置文件
        if config_path is None:
            # 查找配置文件
            possible_paths = [
                Path.cwd() / "config.yaml",
                Path.cwd() / "config.yml",
                Path.home() / ".liteagent" / "config.yaml",
            ]
            for path in possible_paths:
                if path.exists():
                    config_path = str(path)
                    break
        
        if config_path and Path(config_path).exists():
            config._load_from_yaml(config_path)
        
        # 2. 环境变量覆盖
        config._load_from_env()
        
        return config
    
    def _load_from_yaml(self, path: str):
        """从 YAML 文件加载配置"""
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f) or {}
            
            # LLM 配置
            if llm_data := data.get('llm'):
                for key, value in llm_data.items():
                    if hasattr(self.llm, key):
                        setattr(self.llm, key, value)
            
            # Agent 配置
            if agent_data := data.get('agent'):
                for key, value in agent_data.items():
                    if hasattr(self.agent, key):
                        setattr(self.agent, key, value)
            
            # UI 配置
            if ui_data := data.get('ui'):
                for key, value in ui_data.items():
                    if hasattr(self.ui, key):
                        setattr(self.ui, key, value)
                        
        except Exception as e:
            print(f"Warning: Failed to load config file: {e}")
    
    def _load_from_env(self):
        """从环境变量加载配置"""
        env_mapping = {
            'LITE_AGENT_PROVIDER': ('llm', 'provider'),
            'LITE_AGENT_MODEL': ('llm', 'model'),
            'LITE_AGENT_API_BASE': ('llm', 'api_base'),
            'LITE_AGENT_API_KEY': ('llm', 'api_key'),
            'LITE_AGENT_TEMPERATURE': ('llm', 'temperature'),
            'LITE_AGENT_MAX_TOKENS': ('llm', 'max_tokens'),
        }
        
        for env_key, (section, attr) in env_mapping.items():
            if value := os.getenv(env_key):
                config_section = getattr(self, section)
                # 类型转换
                current_value = getattr(config_section, attr)
                if isinstance(current_value, int):
                    value = int(value)
                elif isinstance(current_value, float):
                    value = float(value)
                setattr(config_section, attr, value)
    
    def save(self, path: str = "config.yaml"):
        """保存配置到文件"""
        data = {
            'llm': {
                'provider': self.llm.provider,
                'model': self.llm.model,
                'api_base': self.llm.api_base,
                'api_key': self.llm.api_key,
                'temperature': self.llm.temperature,
                'max_tokens': self.llm.max_tokens,
                'timeout': self.llm.timeout,
                'context_window': self.llm.context_window,
            },
            'agent': {
                'max_iterations': self.agent.max_iterations,
                'max_tool_retries': self.agent.max_tool_retries,
                'tool_timeout': self.agent.tool_timeout,
                'max_context_messages': self.agent.max_context_messages,
                'terminal_timeout': self.agent.terminal_timeout,
                'max_file_size': self.agent.max_file_size,
            },
            'ui': {
                'language': self.ui.language,
                'show_token_usage': self.ui.show_token_usage,
                'color_theme': self.ui.color_theme,
            }
        }
        
        with open(path, 'w', encoding='utf-8') as f:
            yaml.dump(data, f, allow_unicode=True, default_flow_style=False)


# 模型上下文窗口大小映射 (tokens)
MODEL_CONTEXT_WINDOWS = {
    # OpenAI
    "gpt-4o": 128_000,
    "gpt-4o-mini": 128_000,
    "gpt-4-turbo": 128_000,
    "gpt-4": 128_000,
    "gpt-3.5-turbo": 16_385,
    "o1": 200_000,
    "o1-mini": 128_000,
    "o3-mini": 200_000,
    # DeepSeek
    "deepseek-chat": 64_000,
    "deepseek-coder": 128_000,
    "deepseek-reasoner": 64_000,
    "deepseek-v4-flash": 128_000,
    # Anthropic
    "claude-3-5-sonnet": 200_000,
    "claude-3-opus": 200_000,
    "claude-3-haiku": 200_000,
    # Ollama common models
    "gemma4:latest": 128_000,
    "qwen3:4b": 32_768,
    "qwen3.5:4b": 32_768,
    "llama3": 8_192,
    "llama3:8b": 8_192,
    "llama3:70b": 8_192,
    "mistral": 32_768,
    "codellama": 16_384,
}


def get_context_window(model: str) -> int:
    """根据模型名获取上下文窗口大小"""
    # 精确匹配
    if model in MODEL_CONTEXT_WINDOWS:
        return MODEL_CONTEXT_WINDOWS[model]
    # 前缀匹配 (去掉 :latest 等后缀)
    base_model = model.split(':')[0]
    if base_model in MODEL_CONTEXT_WINDOWS:
        return MODEL_CONTEXT_WINDOWS[base_model]
    # 模糊匹配
    for key, value in MODEL_CONTEXT_WINDOWS.items():
        if key in model or model in key:
            return value
    # 提取 provider 前缀匹配 (e.g. deepseek-v4-flash -> deepseek)
    provider_prefix = model.split('-')[0]
    for key, value in MODEL_CONTEXT_WINDOWS.items():
        if key.startswith(provider_prefix):
            return value
    # 默认 128K
    return 128_000


# Provider 预设
PROVIDER_PRESETS = {
    "ollama": {
        "api_base": "http://localhost:11434/v1",
        "models": ["gemma4:latest", "qwen3.5:4b", "qwen3:4b"]
    },
    "openai": {
        "api_base": "https://api.openai.com/v1",
        "models": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo"]
    },
    "deepseek": {
        "api_base": "https://api.deepseek.com/v1",
        "models": ["deepseek-coder", "deepseek-chat"]
    }
}
