#!/usr/bin/env python3
"""
Rabbit Agent CLI - 命令行界面
"""
import asyncio
import sys
import os
import re
from datetime import datetime
from typing import Optional

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt
from rich.theme import Theme
from rich.text import Text
from rich.table import Table
from rich.align import Align
from rich.rule import Rule
from rich.syntax import Syntax
from rich import box

from config import Config, PROVIDER_PRESETS
from agent import Agent
from agent.llm import StreamChunk
from sessions import get_session_manager, SessionManager
from rollback import get_rollback_manager


# Rich 主题
THEME = Theme({
    "info": "cyan",
    "success": "green",
    "warning": "yellow",
    "error": "red bold",
    "agent": "blue bold",
    "user": "green bold",
    "tool": "yellow",
    "dim": "bright_black",
    "accent": "magenta",
    "border": "bright_black",
})

console = Console(theme=THEME)


# 命令定义
COMMANDS = {
    "/help": "显示帮助信息",
    "/quit": "退出程序",
    "/clear": "清屏",
    "/config": "显示当前配置",
    "/tools": "列出所有可用工具",
    "/skills": "列出已加载的技能",
    "/memory": "查看记忆系统状态",
    "/project": "查看项目上下文信息",
    "/status": "显示状态栏",
    "/new": "新建会话",
    "/session": "查看/切换会话",
    "/delete": "删除会话",
    "/save": "保存当前会话",
    "/history": "查看对话历史",
    "/steps": "查看执行步骤",
    "/reset": "重置当前对话",
    "/undo": "撤销上一轮对话",
    "/checkpoints": "查看检查点列表",
}


class AppState:
    def __init__(self):
        self.context_tokens = 0
        self.max_context_tokens = 128000
        self.tool_calls_count = 0
        self.messages_count = 0
        self.current_step = ""
        self.steps_history = []
    
    def add_step(self, step: str):
        self.steps_history.append({
            'time': datetime.now().strftime('%H:%M:%S'),
            'step': step
        })
        self.current_step = step


app_state = AppState()


def show_command_hints(prefix: str = ""):
    """显示命令提示"""
    matching_cmds = []
    for cmd, desc in COMMANDS.items():
        if not prefix or cmd.startswith(prefix.lower()):
            matching_cmds.append((cmd, desc))
    
    if matching_cmds:
        table = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
        table.add_column("命令", style="cyan", min_width=12)
        table.add_column("说明", style="dim")
        
        for cmd, desc in matching_cmds:
            table.add_row(cmd, desc)
        
        console.print(table)


def print_banner():
    """打印欢迎横幅"""
    banner = """
[bold blue]
    ██████╗  █████╗ ██████╗ ██████╗ ██╗████████╗
    ██╔══██╗██╔══██╗██╔══██╗██╔══██╗██║╚══██╔══╝
    ██████╔╝███████║██████╔╝██████╔╝██║   ██║   
    ██╔══██╗██╔══██║██╔══██╗██╔══██╗██║   ██║   
    ██║  ██║██║  ██║██████╔╝██████╔╝██║   ██║   
    ╚═╝  ╚═╝╚═╝  ╚═╝╚═════╝ ╚═════╝ ╚═╝   ╚═╝   
              █████╗  ██████╗ ███████╗███╗   ██╗████████╗
             ██╔══██╗██╔════╝ ██╔════╝████╗  ██║╚══██╔══╝
             ███████║██║  ███╗█████╗  ██╔██╗ ██║   ██║   
             ██╔══██║██║   ██║██╔══╝  ██║╚██╗██║   ██║   
             ██║  ██║╚██████╔╝███████╗██║ ╚████║   ██║   
             ╚═╝  ╚═╝ ╚═════╝ ╚══════╝╚═╝  ╚═══╝   ╚═╝   
[/bold blue]
[bright_black]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/bright_black]
[magenta]                        🐰 本地 AI 编码助手 v0.4.0[/magenta]
[bright_black]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/bright_black]

[cyan]💡 提示:[/cyan]
  • 输入问题开始对话
  • 输入 [magenta]/[/magenta] 查看所有命令
"""
    console.print(banner)


def get_context_bar(usage: float, width: int = 20) -> str:
    """生成进度条"""
    filled = int(usage * width)
    empty = width - filled
    
    if usage < 0.5:
        color = "green"
    elif usage < 0.8:
        color = "yellow"
    else:
        color = "red"
    
    return f"[{color}]{'█' * filled}[/][dim]{'░' * empty}[/]"


def print_status_bar(agent: Agent, session_manager: SessionManager):
    """打印状态栏"""
    if agent.context:
        messages = agent.context.messages
        total_chars = sum(len(m.content or '') for m in messages)
        app_state.context_tokens = total_chars // 4
        app_state.messages_count = len(messages)
    
    usage_pct = app_state.context_tokens / app_state.max_context_tokens if app_state.max_context_tokens > 0 else 0
    context_bar = get_context_bar(usage_pct)
    
    current_session = session_manager.get_current_session()
    session_title = current_session.title[:20] + "..." if current_session and len(current_session.title) > 20 else (current_session.title if current_session else "无")
    
    status_text = (
        f"[cyan]📝 会话:[/cyan] {session_title} │ "
        f"[cyan]📊 上下文:[/cyan] {context_bar} {app_state.context_tokens:,}/{app_state.max_context_tokens:,} ({usage_pct:.1%}) │ "
        f"[cyan]💬 消息:[/cyan] {app_state.messages_count} │ "
        f"[cyan]🔧 工具:[/cyan] {app_state.tool_calls_count}"
    )
    
    console.print()
    console.print(Panel(
        status_text,
        border_style="bright_black",
        padding=(0, 1),
        title="[dim]状态[/dim]",
        title_align="left"
    ))


def print_agent_header():
    """打印 Agent 头部"""
    console.print()
    console.print(Panel(
        "[bold blue]🐰 Rabbit Agent[/bold blue]",
        border_style="blue",
        padding=(0, 1)
    ))


def print_tool_call(tool_name: str, arguments: dict = None):
    """打印工具调用"""
    app_state.tool_calls_count += 1
    app_state.add_step(f"调用工具: {tool_name}")
    
    tool_icons = {
        'terminal': '💻', 'read_file': '📖', 'write_file': '✏️',
        'edit_file': '📝', 'list_directory': '📁', 'search_files': '🔍',
    }
    
    icon = tool_icons.get(tool_name, '🔧')
    
    args_preview = ""
    if arguments:
        key_args = []
        for key in ['path', 'command', 'pattern']:
            if key in arguments:
                value = str(arguments[key])
                if len(value) > 40:
                    value = value[:37] + "..."
                key_args.append(f"{key}={value}")
        if key_args:
            args_preview = f" ({', '.join(key_args)})"
    
    console.print(f"\n  {icon} [yellow]{tool_name}[/yellow][dim]{args_preview}[/dim]")


def render_markdown(content: str):
    """渲染 Markdown"""
    if not content:
        return
    
    parts = re.split(r'(```[\s\S]*?```)', content)
    
    for part in parts:
        if part.startswith('```') and part.endswith('```'):
            lines = part[3:-3].strip().split('\n')
            if lines:
                lang = lines[0].strip() if lines[0].strip() and not lines[0].strip().startswith(' ') else ''
                code = '\n'.join(lines[1:]) if lang else '\n'.join(lines)
                
                try:
                    syntax = Syntax(code, lang or "text", theme="monokai", line_numbers=True, word_wrap=True, padding=(1, 2))
                    console.print(Panel(syntax, border_style="bright_black", padding=0))
                except:
                    console.print(Panel(code, border_style="bright_black", padding=(1, 2)))
        else:
            if part.strip():
                try:
                    md = Markdown(part)
                    console.print(md)
                except:
                    console.print(part)


class StreamCollector:
    def __init__(self):
        self.buffer = ""
        self.tool_calls = []
    
    def add_content(self, content: str):
        self.buffer += content
    
    def add_tool_call(self, tool_call):
        self.tool_calls.append(tool_call)
    
    def get_content(self) -> str:
        return self.buffer
    
    def clear(self):
        self.buffer = ""
        self.tool_calls = []


stream_collector = StreamCollector()


async def stream_handler(chunk: StreamChunk):
    global stream_collector
    
    if chunk.content:
        stream_collector.add_content(chunk.content)
    
    if chunk.tool_calls:
        for tc in chunk.tool_calls:
            stream_collector.add_tool_call(tc)
            print_tool_call(tc.name, tc.arguments)


def print_sessions(session_manager: SessionManager):
    sessions = session_manager.list_sessions()
    current_id = session_manager.current_session_id
    
    if not sessions:
        console.print("\n[yellow]📭 暂无会话，输入 /new 新建会话[/yellow]\n")
        return None
    
    table = Table(
        title="📝 会话列表",
        box=box.ROUNDED,
        border_style="bright_black",
        title_style="bold magenta",
        show_header=True,
        header_style="bold cyan",
        padding=(0, 1)
    )
    table.add_column("#", style="bright_black", width=3)
    table.add_column("状态", style="bright_black", width=4)
    table.add_column("标题", style="white", min_width=30)
    table.add_column("消息数", style="cyan", justify="right", width=6)
    table.add_column("最后更新", style="dim", width=20)
    
    for i, session in enumerate(sessions, 1):
        is_current = session.id == current_id
        status = "▶️" if is_current else "  "
        
        title = session.title[:35] + "..." if len(session.title) > 35 else session.title
        msg_count = len(session.messages)
        
        try:
            dt = datetime.fromisoformat(session.updated_at)
            time_str = dt.strftime("%m-%d %H:%M")
        except:
            time_str = session.updated_at[:16]
        
        table.add_row(str(i), status, title, str(msg_count), time_str)
    
    console.print()
    console.print(table)
    console.print()
    
    return sessions


async def handle_session_command(command: str, agent: Agent, session_manager: SessionManager):
    global app_state
    
    if command == "/new":
        title = Prompt.ask("\n[cyan]会话标题[/cyan] (留空自动生成)", default="")
        session = session_manager.create_session(title if title else None)
        
        agent.context.messages.clear()
        agent.context.add_system_message("你是一个强大的 AI 编码助手（Rabbit Agent）。")
        app_state = AppState()
        
        console.print(f"\n[green]✅ 已创建新会话: {session.title}[/green]\n")
        return True
    
    elif command == "/session":
        sessions = print_sessions(session_manager)
        
        if sessions:
            choice = Prompt.ask("\n[cyan]输入会话编号切换 (留空返回)[/cyan]", default="")
            
            if choice.strip():
                try:
                    idx = int(choice) - 1
                    if 0 <= idx < len(sessions):
                        session = sessions[idx]
                        session_manager.switch_session(session.id)
                        
                        agent.context.messages.clear()
                        agent.context.add_system_message("你是一个强大的 AI 编码助手（Rabbit Agent）。")
                        
                        for msg in session.messages:
                            if msg["role"] == "user":
                                agent.context.add_user_message(msg["content"])
                            elif msg["role"] == "assistant":
                                agent.context.add_assistant_message(msg["content"])
                        
                        app_state = AppState()
                        console.print(f"\n[green]✅ 已切换到会话: {session.title}[/green]\n")
                    else:
                        console.print("\n[yellow]⚠️ 无效的会话编号[/yellow]\n")
                except ValueError:
                    console.print("\n[yellow]⚠️ 请输入数字[/yellow]\n")
        
        return True
    
    elif command == "/delete":
        sessions = print_sessions(session_manager)
        
        if sessions:
            choice = Prompt.ask("\n[cyan]输入要删除的会话编号 (留空取消)[/cyan]", default="")
            
            if choice.strip():
                try:
                    idx = int(choice) - 1
                    if 0 <= idx < len(sessions):
                        session = sessions[idx]
                        
                        confirm = Prompt.ask(f"\n[yellow]确定删除会话 \"{session.title}\" 吗? (y/n)[/yellow]", default="n")
                        
                        if confirm.lower() == "y":
                            session_manager.delete_session(session.id)
                            
                            if session.id == session_manager.current_session_id:
                                agent.context.messages.clear()
                                agent.context.add_system_message("你是一个强大的 AI 编码助手（Rabbit Agent）。")
                                app_state = AppState()
                            
                            console.print(f"\n[green]✅ 已删除会话: {session.title}[/green]\n")
                        else:
                            console.print("\n[dim]已取消删除[/dim]\n")
                    else:
                        console.print("\n[yellow]⚠️ 无效的会话编号[/yellow]\n")
                except ValueError:
                    console.print("\n[yellow]⚠️ 请输入数字[/yellow]\n")
        
        return True
    
    elif command == "/save":
        current_session = session_manager.get_current_session()
        if current_session:
            session_manager.update_session(
                current_session.id,
                messages=[{"role": m.role, "content": m.content} for m in agent.context.messages if m.role in ["user", "assistant"]]
            )
            console.print(f"\n[green]✅ 会话已保存: {current_session.title}[/green]\n")
        else:
            console.print("\n[yellow]⚠️ 没有活跃的会话[/yellow]\n")
        return True
    
    return False


def print_help():
    table = Table(
        title="📖 命令帮助",
        box=box.ROUNDED,
        border_style="bright_black",
        title_style="bold magenta",
        show_header=True,
        header_style="bold cyan",
        padding=(0, 2)
    )
    table.add_column("命令", style="magenta", min_width=15)
    table.add_column("说明", style="white")
    
    commands = [
        ("/help, /h", "显示帮助信息"),
        ("/quit, /q", "退出程序"),
        ("/clear, /c", "清屏"),
        ("/config", "显示当前配置"),
        ("/tools", "列出所有可用工具"),
        ("/skills", "列出已加载的技能"),
        ("/memory", "查看记忆系统状态"),
        ("/project", "查看项目上下文信息"),
        ("/status", "显示状态栏"),
        ("", ""),
        ("[bold]会话管理[/bold]", ""),
        ("/new", "新建会话"),
        ("/session", "查看/切换会话"),
        ("/delete", "删除会话"),
        ("/save", "保存当前会话"),
        ("", ""),
        ("[bold]其他[/bold]", ""),
        ("/history", "查看对话历史"),
        ("/steps", "查看执行步骤"),
        ("/reset", "重置当前对话"),
    ]
    
    for cmd, desc in commands:
        if cmd or desc:
            table.add_row(cmd, desc)
    
    console.print()
    console.print(table)


async def run_cli_mode(config: Config, command: str = None):
    """CLI 模式主循环"""
    global app_state
    agent = Agent(config)
    
    try:
        if command:
            # 单次查询模式
            await agent.initialize()
            stream_collector.clear()
            print_agent_header()
            
            response = await agent.run(command, stream_callback=stream_handler)
            
            console.print()
            render_markdown(stream_collector.get_content())
            console.print()
            console.print(Rule(style="bright_black"))
        else:
            # 交互式模式
            print_banner()
            
            with console.status("[bold cyan]正在初始化...[/bold cyan]", spinner="dots"):
                await agent.initialize()
            
            session_manager = get_session_manager()
            if not session_manager.current_session_id:
                session_manager.create_session("新会话")
            
            from plugins import get_plugin_manager
            pm = get_plugin_manager()
            skills_count = len(pm.list_skills())
            
            console.print(f"  [cyan]Provider:[/cyan] {config.llm.provider}")
            console.print(f"  [cyan]Model:[/cyan] {config.llm.model}")
            console.print(f"  [cyan]工具数:[/cyan] 25 个")
            console.print(f"  [cyan]技能数:[/cyan] {skills_count} 个")
            console.print()
            console.print(Rule(style="bright_black"))
            print_status_bar(agent, session_manager)
            
            while True:
                try:
                    stream_collector.clear()
                    
                    console.print()
                    user_input = Prompt.ask("\n[bold green]❯[/bold green] [green]You[/green]")
                    
                    if not user_input or not user_input.strip():
                        continue
                    
                    user_input = user_input.strip()
                    
                    if user_input.startswith("/"):
                        command = user_input.lower()
                        
                        if command in ["/quit", "/q", "/exit"]:
                            await handle_session_command("/save", agent, session_manager)
                            console.print("\n[cyan]👋 再见！[/cyan]\n")
                            break
                        elif command in ["/help", "/h", "/?"]:
                            print_help()
                            continue
                        elif command in ["/clear", "/c", "/cls"]:
                            console.clear()
                            print_banner()
                            print_status_bar(agent, session_manager)
                            continue
                        elif command == "/config":
                            table = Table(title="⚙️ 当前配置", box=box.ROUNDED, border_style="bright_black", title_style="bold magenta")
                            table.add_column("配置项", style="cyan", min_width=15)
                            table.add_column("值", style="white")
                            table.add_row("Provider", config.llm.provider)
                            table.add_row("Model", config.llm.model)
                            table.add_row("API Base", config.llm.api_base)
                            table.add_row("Temperature", str(config.llm.temperature))
                            table.add_row("Max Tokens", str(config.llm.max_tokens))
                            console.print(table)
                            continue
                        elif command == "/tools":
                            from tools.registry import registry
                            table = Table(title="🛠️ 可用工具", box=box.ROUNDED, border_style="bright_black", title_style="bold magenta", show_header=True, header_style="bold cyan", padding=(0, 1))
                            table.add_column("#", style="bright_black", width=3)
                            table.add_column("工具名", style="magenta", min_width=20)
                            table.add_column("说明", style="white")
                            for i, tool in enumerate(registry.list_tools(), 1):
                                desc = tool.description[:60] + "..." if len(tool.description) > 60 else tool.description
                                table.add_row(str(i), tool.name, desc)
                            console.print(table)
                            continue
                        elif command == "/skills":
                            from plugins import get_plugin_manager
                            pm = get_plugin_manager()
                            skills = pm.list_skills()
                            table = Table(title="🔌 已加载技能", box=box.ROUNDED, border_style="bright_black", title_style="bold magenta", show_header=True, header_style="bold cyan", padding=(0, 1))
                            table.add_column("#", style="bright_black", width=3)
                            table.add_column("技能名", style="magenta", min_width=20)
                            table.add_column("说明", style="white", max_width=40)
                            table.add_column("触发词", style="dim")
                            for i, skill in enumerate(skills, 1):
                                triggers = ", ".join(skill["triggers"][:3])
                                desc = skill["description"][:35] + "..." if len(skill["description"]) > 35 else skill["description"]
                                table.add_row(str(i), skill["name"], desc, triggers)
                            console.print(table)
                            continue
                        elif command == "/memory":
                            from memory import MemoryManager
                            memory = MemoryManager()
                            stats = memory.store.get_stats()
                            table = Table(title="🧠 记忆系统", box=box.ROUNDED, border_style="bright_black", title_style="bold magenta", show_header=True, header_style="bold cyan", padding=(0, 1))
                            table.add_column("类别", style="magenta")
                            table.add_column("数量", style="white", justify="right")
                            for cat, desc in {"conversation": "对话历史", "preference": "用户偏好", "project": "项目信息", "knowledge": "知识库"}.items():
                                table.add_row(desc, str(stats.get(cat, 0)))
                            table.add_row("总计", str(stats.get("total", 0)), style="bold")
                            console.print(table)
                            continue
                        elif command == "/project":
                            from context import get_project_context
                            context = get_project_context()
                            console.print(Panel(context, title="[bold cyan]📁 项目上下文[/bold cyan]", border_style="bright_black", padding=(1, 2)))
                            continue
                        elif command == "/status":
                            print_status_bar(agent, session_manager)
                            continue
                        elif command in ["/new", "/session", "/delete", "/save"]:
                            handled = await handle_session_command(command, agent, session_manager)
                            if handled:
                                print_status_bar(agent, session_manager)
                            continue
                        elif command == "/history":
                            msgs = [m for m in agent.context.messages if m.role in ["user", "assistant"]]
                            if msgs:
                                table = Table(title="📜 对话历史", box=box.SIMPLE)
                                table.add_column("角色", style="bold", width=8)
                                table.add_column("内容", max_width=70)
                                for m in msgs[-10:]:
                                    role = "[green]You[/green]" if m.role == "user" else "[blue]Agent[/blue]"
                                    content = m.content[:70] + "..." if len(m.content) > 70 else m.content
                                    table.add_row(role, content)
                                console.print(table)
                            else:
                                console.print("[bright_black]暂无对话历史[/bright_black]")
                            continue
                        elif command == "/steps":
                            if app_state.steps_history:
                                table = Table(title="⚡ 执行步骤", box=box.SIMPLE)
                                table.add_column("时间", style="dim", width=10)
                                table.add_column("步骤", style="white")
                                for step in app_state.steps_history[-15:]:
                                    table.add_row(step['time'], step['step'])
                                console.print(table)
                            else:
                                console.print("[bright_black]暂无执行步骤[/bright_black]")
                            continue
                        elif command == "/reset":
                            agent.context.messages.clear()
                            agent.context.add_system_message("你是一个强大的 AI 编码助手（Rabbit Agent）。")
                            app_state = AppState()
                            console.print("\n[green]✅ 对话已重置[/green]\n")
                            print_status_bar(agent, session_manager)
                            continue
                        elif command == "/undo":
                            # 撤销上一轮对话
                            rollback_mgr = get_rollback_manager()
                            checkpoints = rollback_mgr.list_checkpoints()
                            
                            if len(checkpoints) < 2:
                                console.print("\n[yellow]⚠️ 没有可撤销的操作[/yellow]\n")
                            else:
                                # 显示将要撤销的内容
                                current = checkpoints[-1]
                                console.print(f"\n[cyan]正在撤销: {current.description}[/cyan]")
                                console.print(f"[dim]文件变更: {len(current.file_changes)} 个[/dim]")
                                
                                # 执行回滚
                                target = rollback_mgr.rollback_last()
                                
                                if target:
                                    # 恢复消息历史
                                    agent.context.messages.clear()
                                    agent.context.add_system_message("你是一个强大的 AI 编码助手（Rabbit Agent）。")
                                    
                                    # 从会话中恢复消息
                                    current_session = session_manager.get_current_session()
                                    if current_session:
                                        # 截断到目标检查点的消息数
                                        messages_to_keep = target.messages_count
                                        current_session.messages = current_session.messages[:messages_to_keep]
                                        session_manager._save_session(current_session)
                                        
                                        # 恢复消息到 Agent
                                        for msg in current_session.messages:
                                            if msg["role"] == "user":
                                                agent.context.add_user_message(msg["content"])
                                            elif msg["role"] == "assistant":
                                                agent.context.add_assistant_message(msg["content"])
                                    
                                    console.print(f"[green]✅ 已撤销到: {target.description}[/green]\n")
                                else:
                                    console.print("\n[red]❌ 撤销失败[/red]\n")
                            
                            print_status_bar(agent, session_manager)
                            continue
                        elif command == "/checkpoints":
                            # 显示检查点列表
                            rollback_mgr = get_rollback_manager()
                            checkpoints = rollback_mgr.list_checkpoints()
                            
                            if not checkpoints:
                                console.print("\n[yellow]暂无检查点[/yellow]\n")
                            else:
                                table = Table(
                                    title="📸 检查点列表",
                                    box=box.ROUNDED,
                                    border_style="bright_black",
                                    title_style="bold magenta",
                                    show_header=True,
                                    header_style="bold cyan",
                                    padding=(0, 1)
                                )
                                table.add_column("#", style="bright_black", width=3)
                                table.add_column("状态", style="bright_black", width=4)
                                table.add_column("描述", style="white", min_width=30)
                                table.add_column("消息数", style="cyan", justify="right", width=6)
                                table.add_column("文件变更", style="yellow", justify="right", width=8)
                                table.add_column("时间", style="dim", width=20)
                                
                                for i, cp in enumerate(checkpoints):
                                    is_current = i == len(checkpoints) - 1
                                    status = "▶️" if is_current else "  "
                                    
                                    try:
                                        dt = datetime.fromisoformat(cp.timestamp)
                                        time_str = dt.strftime("%m-%d %H:%M")
                                    except:
                                        time_str = cp.timestamp[:16]
                                    
                                    table.add_row(
                                        str(i + 1),
                                        status,
                                        cp.description[:40],
                                        str(cp.messages_count),
                                        str(len(cp.file_changes)),
                                        time_str
                                    )
                                
                                console.print()
                                console.print(table)
                                console.print()
                                console.print("[dim]使用 /undo 撤销最后一轮对话[/dim]\n")
                            
                            continue
                        elif command == "/":
                            show_command_hints()
                            continue
                        else:
                            console.print(f"\n[yellow]⚠️ 未知命令: {command}[/yellow]")
                            show_command_hints(command)
                            continue
                    
                    # 保存用户消息
                    session_manager.add_message(session_manager.current_session_id, "user", user_input)
                    app_state.add_step("处理用户输入")
                    
                    print_agent_header()
                    
                    response = await agent.run(user_input, stream_callback=stream_handler)
                    
                    if response:
                        session_manager.add_message(session_manager.current_session_id, "assistant", response)
                        
                        # 创建检查点
                        rollback_mgr = get_rollback_manager()
                        current_session = session_manager.get_current_session()
                        messages_count = len(current_session.messages) if current_session else 0
                        rollback_mgr.create_checkpoint(
                            description=user_input[:50],
                            messages_count=messages_count
                        )
                    
                    console.print()
                    render_markdown(stream_collector.get_content())
                    
                    console.print()
                    app_state.add_step("完成")
                    print_status_bar(agent, session_manager)
                    console.print(Rule(style="bright_black"))
                    
                except KeyboardInterrupt:
                    console.print("\n\n[cyan]👋 再见！[/cyan]\n")
                    break
                except EOFError:
                    console.print("\n[cyan]👋 再见！[/cyan]\n")
                    break
                except Exception as e:
                    console.print(f"\n[red bold]❌ 错误: {str(e)}[/red bold]\n")
                    continue
    
    finally:
        await agent.close()
