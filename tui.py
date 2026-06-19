#!/usr/bin/env python3
"""
Rabbit Agent TUI - 基于 prompt_toolkit 的交互式终端界面
"""
import asyncio
import json
import os
import sys
from datetime import datetime

from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.styles import Style
from prompt_toolkit.formatted_text import ANSI as ANSI_TEXT, HTML
from prompt_toolkit.patch_stdout import patch_stdout
from prompt_toolkit import print_formatted_text

from config import Config
from agent import Agent
from sessions import get_session_manager
from logger import logger

# ── ANSI 颜色定义 ──────────────────────────────────────────────
COLORS = {
    "red": "\033[91m",
    "green": "\033[92m",
    "yellow": "\033[93m",
    "blue": "\033[94m",
    "magenta": "\033[95m",
    "cyan": "\033[96m",
    "white": "\033[97m",
    "dim": "\033[90m",
    "bold": "\033[1m",
    "reset": "\033[0m",
    "bg_blue": "\033[44m",
    "bg_green": "\033[42m",
    "bg_yellow": "\033[43m",
    "bg_red": "\033[41m",
    "bg_cyan": "\033[46m",
    "underline": "\033[4m",
    "italic": "\033[3m",
}
RESET = "\033[0m"


def color_print(text, color="white"):
    """带颜色打印"""
    color_code = COLORS.get(color, "")
    try:
        print_formatted_text(ANSI_TEXT(f"{color_code}{text}{RESET}"))
    except Exception:
        print(f"{color_code}{text}{RESET}")


def color_print_inline(text, color="white"):
    """带颜色打印（不换行）"""
    color_code = COLORS.get(color, "")
    try:
        print_formatted_text(ANSI_TEXT(f"{color_code}{text}{RESET}"), end="")
    except Exception:
        print(f"{color_code}{text}{RESET}", end="")


def color_print_multi(*parts):
    """多色打印: color_print_multi(('text', 'color'), ('text2', 'color2'))"""
    line = ""
    for text, color in parts:
        color_code = COLORS.get(color, "")
        line += f"{color_code}{text}{RESET}"
    try:
        print_formatted_text(ANSI_TEXT(line))
    except Exception:
        print(line)


# ── 符号定义 ──────────────────────────────────────────────────
SYMBOLS = {
    "box_h": "─",
    "box_v": "│",
    "box_tl": "┌",
    "box_tr": "┐",
    "box_bl": "└",
    "box_br": "┘",
    "box_ml": "├",
    "box_mr": "┤",
    "dot": "●",
    "arrow": "▸",
    "check": "✓",
    "cross": "✗",
    "star": "★",
    "bullet": "◆",
    "line": "━",
}

# ── 命令列表 ──────────────────────────────────────────────────
COMMANDS = {
    "/help": "Show commands",
    "/quit": "Exit",
    "/clear": "Clear screen",
    "/config": "Show config",
    "/tools": "List tools",
    "/skills": "List skills",
    "/memory": "Memory stats",
    "/status": "Show status",
    "/new": "New session",
    "/save": "Save session",
    "/history": "Show history",
    "/reset": "Reset counters",
    "/session": "Switch session",
    "/delete": "Delete session",
}

PROMPT_STYLE = Style.from_dict({
    "prompt": "ansicyan bold",
    "prompt.user": "ansigreen bold",
    "prompt.arrow": "ansiyellow",
})

BOX_WIDTH = 56


# ── Markdown 渲染 ─────────────────────────────────────────────
def render_markdown_ansi(text: str) -> str:
    """
    用 Rich 渲染 Markdown 为 ANSI 字符串。
    """
    from rich.console import Console
    from rich.markdown import Markdown
    from io import StringIO

    buf = StringIO()
    console = Console(file=buf, force_terminal=True, width=70, no_color=False)
    console.print(Markdown(text))
    return buf.getvalue()


# ── 命令补全器 ────────────────────────────────────────────────
class CommandCompleter(Completer):
    """斜杠命令自动补全"""

    def __init__(self, commands):
        self.commands = commands

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor
        if text.startswith("/"):
            for cmd, desc in self.commands.items():
                if cmd.startswith(text):
                    yield Completion(cmd, start_position=-len(text), display_meta=desc)


# ── 流式输出缓冲 ──────────────────────────────────────────────
class StreamBuffer:
    """收集流式输出的文本和工具调用"""

    def __init__(self):
        self.text = ""
        self.tool_calls = []

    def clear(self):
        self.text = ""
        self.tool_calls = []

    def add_content(self, content):
        self.text += content

    def add_tool_call(self, name, args):
        self.tool_calls.append((name, args))


# ── 辅助绘图函数 ──────────────────────────────────────────────
def draw_box(title, lines, width=BOX_WIDTH):
    """绘制带标题的盒子"""
    title_len = len(title)
    padding = width - title_len - 4
    color_print(
        f"  {COLORS['cyan']}{SYMBOLS['box_tl']}{SYMBOLS['box_h'] * 2} "
        f"{COLORS['bold']}{title}{RESET}"
        f"{COLORS['cyan']}{SYMBOLS['box_h'] * padding}{SYMBOLS['box_tr']}{RESET}"
    )
    for line in lines:
        line_len = len(line)
        pad = width - line_len - 3
        color_print(
            f"  {COLORS['cyan']}{SYMBOLS['box_v']}{RESET} {line}"
            f"{' ' * pad}{COLORS['cyan']}{SYMBOLS['box_v']}{RESET}"
        )
    color_print(
        f"  {COLORS['cyan']}{SYMBOLS['box_bl']}{SYMBOLS['box_h'] * width}{SYMBOLS['box_br']}{RESET}"
    )


def draw_divider(char="─", width=BOX_WIDTH, color="dim"):
    """绘制分隔线"""
    color_print(f"  {COLORS[color]}{char * width}{RESET}")


def make_tag(text, bg="cyan"):
    """生成标签样式"""
    bg_color = COLORS.get(f"bg_{bg}", "")
    return f"{bg_color}{COLORS['bold']} {text} {RESET}"


# ── 主 TUI 类 ────────────────────────────────────────────────
class RabbitTUI:
    """Rabbit Agent 交互式终端界面"""

    def __init__(self, config):
        self.config = config
        self.agent = Agent(config)
        self.session_mgr = get_session_manager()
        self.tool_count = 0
        self.msg_count = 0
        self.buffer = StreamBuffer()
        self.running = True
        self.start_time = datetime.now()
        self.last_tool = ""
        self._width = BOX_WIDTH

    # ── 状态信息 ──────────────────────────────────────────────

    def elapsed_time(self):
        """获取已运行时间"""
        seconds = int((datetime.now() - self.start_time).total_seconds())
        if seconds < 60:
            return f"{seconds}s"
        return f"{seconds // 60}m{seconds % 60}s"

    def context_bar(self):
        """生成上下文占用进度条"""
        from config import get_context_window

        model = self.config.llm.model
        max_tokens = (
            self.config.llm.context_window
            if self.config.llm.context_window > 0
            else get_context_window(model)
        )

        # 估算已用 token
        used_tokens = 0
        usage = self.agent.last_usage if self.agent else {}
        if usage and usage.get("prompt_tokens"):
            used_tokens = usage["prompt_tokens"]
        elif self.agent and self.agent.context:
            total_chars = sum(len(m.content or "") for m in self.agent.context.messages)
            used_tokens = total_chars // 3

        pct = min(used_tokens / max_tokens, 1.0) if max_tokens > 0 else 0
        bar_len = 15
        filled = int(pct * bar_len)

        # 颜色根据占用率变化
        if pct >= 0.8:
            bar = f"{COLORS['red']}{'█' * filled}{COLORS['dim']}{'░' * (bar_len - filled)}{RESET}"
        elif pct >= 0.6:
            bar = f"{COLORS['yellow']}{'█' * filled}{COLORS['dim']}{'░' * (bar_len - filled)}{RESET}"
        else:
            bar = f"{COLORS['green']}{'█' * filled}{COLORS['dim']}{'░' * (bar_len - filled)}{RESET}"

        def fmt_number(n):
            if n >= 1000:
                return f"{n / 1000:.1f}K"
            return str(n)

        warn = ""
        if pct >= 0.9:
            warn = f" {COLORS['red']}⚠{RESET}"
        elif pct >= 0.7:
            warn = f" {COLORS['yellow']}△{RESET}"

        return f"{bar} {fmt_number(used_tokens)}/{fmt_number(max_tokens)} ({pct * 100:.0f}%){warn}"

    # ── 界面显示 ──────────────────────────────────────────────

    def show_banner(self):
        """显示启动横幅"""
        width = self._width
        print()
        logo = [
            f"{COLORS['cyan']}{COLORS['bold']}  ╦═╗╔═╗╔═╗╔╦╗╦╔╦╗╔═╗  ╔═╗╔═╗╔╦╗╔═╗╦═╗{RESET}",
            f"{COLORS['cyan']}{COLORS['bold']}  ╠╦╝║╣ ╚═╗ ║ ║║║║║ ║  ║ ╦║╣  ║ ║╣ ╠╦╝{RESET}",
            f"{COLORS['cyan']}  ╩╚═╚═╝╚═╝ ╩ ╩╩ ╩╚═╝  ╚═╝╚═╝ ╩ ╚═╝╩╚═{RESET}",
        ]
        for line in logo:
            color_print(line)
        print()
        draw_box("Info", [
            f"{make_tag('v1.0')} {COLORS['white']}Rabbit Agent TUI{RESET}",
            f"{make_tag('cmd')} {COLORS['dim']}Type /help for commands{RESET}",
            f"{make_tag('exit')} {COLORS['dim']}/quit or Ctrl+D{RESET}",
        ], width)
        print()

    def show_status(self):
        """显示状态栏"""
        width = self._width
        tool_count_str = f"{COLORS['yellow']}{self.tool_count}{RESET}"
        msg_count_str = f"{COLORS['cyan']}{self.msg_count}{RESET}"
        elapsed_str = f"{COLORS['green']}{self.elapsed_time()}{RESET}"
        ctx = self.context_bar()

        line = (
            f"  {COLORS['dim']}Tools:{RESET} {tool_count_str} "
            f"{COLORS['dim']}│{RESET} "
            f"{COLORS['dim']}Msgs:{RESET} {msg_count_str} "
            f"{COLORS['dim']}│{RESET} "
            f"{COLORS['dim']}Time:{RESET} {elapsed_str}"
        )
        color_print(line)
        color_print(f"  {COLORS['dim']}Context:{RESET} {ctx}")
        draw_divider("─", width)

    def show_help(self):
        """显示帮助信息"""
        width = self._width
        print()
        lines = []
        for cmd, desc in COMMANDS.items():
            lines.append(f"{COLORS['cyan']}{cmd:<14}{RESET} {COLORS['white']}{desc}{RESET}")
        draw_box("Commands", lines, width)
        print()

    def show_config(self):
        """显示当前配置"""
        width = self._width
        print()
        draw_box("Config", [
            f"{COLORS['cyan']}Provider:{RESET} {COLORS['white']}{self.config.llm.provider}{RESET}",
            f"{COLORS['cyan']}Model:{RESET}    {COLORS['white']}{self.config.llm.model}{RESET}",
            f"{COLORS['cyan']}API Base:{RESET} {COLORS['dim']}{self.config.llm.api_base}{RESET}",
            f"{COLORS['cyan']}Max Tokens:{RESET} {COLORS['white']}{self.config.llm.max_tokens}{RESET}",
        ], width)
        print()

    def show_tools(self):
        """显示工具列表"""
        from tools.registry import registry

        width = self._width
        print()
        lines = []
        for i, tool_def in enumerate(registry.list_tools(), 1):
            desc = tool_def.description[:35] + "..." if len(tool_def.description) > 35 else tool_def.description
            lines.append(
                f"{COLORS['yellow']}{i:>2}.{RESET} "
                f"{COLORS['white']}{tool_def.name:<16}{RESET} "
                f"{COLORS['dim']}{desc}{RESET}"
            )
        draw_box(f"Tools ({len(lines)})", lines, width)
        print()

    def show_skills(self):
        """显示技能列表"""
        from plugins import get_plugin_manager

        width = self._width
        skills = get_plugin_manager().list_skills()
        print()
        lines = []
        for i, skill in enumerate(skills, 1):
            lines.append(f"{COLORS['yellow']}{i:>2}.{RESET} {COLORS['white']}{skill['name']}{RESET}")
        draw_box(f"Skills ({len(lines)})", lines, width)
        print()

    def show_memory(self):
        """显示记忆统计"""
        from memory import MemoryManager

        width = self._width
        stats = MemoryManager().store.get_stats()
        print()
        icons = {
            "conversation": "💬",
            "preference": "⚙️",
            "project": "📁",
            "knowledge": "📚",
        }
        lines = []
        for category in ["conversation", "preference", "project", "knowledge"]:
            icon = icons.get(category, "•")
            count = stats.get(category, 0)
            lines.append(
                f"{icon} {COLORS['cyan']}{category:<14}{RESET} {COLORS['white']}{count}{RESET}"
            )
        draw_box("Memory", lines, width)
        print()

    def show_history(self):
        """显示对话历史"""
        if not self.agent.context:
            color_print("  No history", "dim")
            return

        messages = [m for m in self.agent.context.messages if m.role in ["user", "assistant"]]
        width = self._width
        print()
        lines = []
        for msg in messages[-6:]:
            if msg.role == "user":
                text = msg.content[:45] + "..." if len(msg.content) > 45 else msg.content
                lines.append(f"{COLORS['green']}You{RESET} {COLORS['dim']}▸{RESET} {text}")
            else:
                text = msg.content[:45] + "..." if len(msg.content) > 45 else msg.content
                lines.append(f"{COLORS['blue']}AI{RESET}  {COLORS['dim']}▸{RESET} {text}")
        draw_box(f"History ({len(messages)} msgs)", lines, width)
        print()

    # ── 会话管理 ──────────────────────────────────────────────

    async def switch_session(self):
        """切换会话（方向键选择）"""
        sessions = self.session_mgr.list_sessions()
        if not sessions:
            print()
            color_print("  No sessions", "dim")
            print()
            return

        current_idx = 0
        for i, sess in enumerate(sessions):
            if sess.id == self.session_mgr.current_session_id:
                current_idx = i
                break

        idx = await self._pick_with_arrow(
            sessions, current_idx,
            header="  Sessions: ↑↓ select, Enter switch, Esc cancel"
        )
        if idx is None:
            color_print("  Cancelled", "dim")
            print()
            return

        target = sessions[idx]
        self.session_mgr.switch_session(target.id)
        color_print(f"  {SYMBOLS['check']} Switched to: {target.title}", "green")
        print()

    async def delete_session(self, cmd):
        """删除会话（方向键选择）"""
        sessions = self.session_mgr.list_sessions()
        if not sessions:
            print()
            color_print("  No sessions to delete", "dim")
            print()
            return

        current_idx = 0
        for i, sess in enumerate(sessions):
            if sess.id == self.session_mgr.current_session_id:
                current_idx = i
                break

        idx = await self._pick_with_arrow(
            sessions, current_idx,
            header="  Delete: ↑↓ select, Enter delete, Esc cancel"
        )
        if idx is None:
            color_print("  Cancelled", "dim")
            print()
            return

        target = sessions[idx]
        if self.session_mgr.delete_session(target.id):
            color_print(f"  {SYMBOLS['check']} Deleted: {target.title}", "green")
            new_session = self.session_mgr.get_current_session()
            if new_session:
                color_print(f"  {SYMBOLS['arrow']} Current: {new_session.title}", "cyan")
            else:
                color_print("  No sessions left. Use /new", "dim")
        else:
            color_print(f"  {SYMBOLS['cross']} Delete failed", "red")
        print()

    async def _pick_with_arrow(self, sessions, current_idx=0, header=""):
        """方向键选择器（prompt_toolkit Application）"""
        from prompt_toolkit import Application
        from prompt_toolkit.key_binding import KeyBindings
        from prompt_toolkit.layout import Layout
        from prompt_toolkit.layout.containers import Window
        from prompt_toolkit.layout.controls import FormattedTextControl
        from prompt_toolkit.formatted_text import FormattedText

        selected = [current_idx]
        result = [None]

        def get_text():
            lines = [
                ("class:header", header + "\n"),
                ("", "  " + "─" * 50 + "\n"),
            ]
            for i, sess in enumerate(sessions):
                marker = SYMBOLS["arrow"] if i == selected[0] else " "
                msg_count = len(sess.messages)
                title = sess.title[:30] + "..." if len(sess.title) > 30 else sess.title
                line = f"  {marker} [{sess.id}] {title} ({msg_count} msgs)"
                if i == selected[0]:
                    lines.append(("class:selected", line + "\n"))
                else:
                    lines.append(("", line + "\n"))
            return FormattedText(lines)

        control = FormattedTextControl(get_text)
        body = Window(content=control)
        bindings = KeyBindings()

        @bindings.add("up")
        def _(event):
            selected[0] = (selected[0] - 1) % len(sessions)

        @bindings.add("down")
        def _(event):
            selected[0] = (selected[0] + 1) % len(sessions)

        @bindings.add("enter")
        def _(event):
            result[0] = selected[0]
            event.app.exit()

        @bindings.add("escape")
        def _(event):
            event.app.exit()

        @bindings.add("q")
        def _(event):
            event.app.exit()

        app = Application(
            layout=Layout(body),
            key_bindings=bindings,
            style=Style.from_dict({
                "selected": "ansicyan bold reverse",
                "header": "ansiyellow",
            }),
            full_screen=False,
        )
        await app.run_async()
        return result[0]

    # ── 流式输出处理 ──────────────────────────────────────────

    async def handle_stream_chunk(self, chunk):
        """处理流式输出事件"""
        event = getattr(chunk, "event_type", "")

        # 状态事件
        if event == "status":
            print()
            color_print(f"  {COLORS['cyan']}{SYMBOLS['dot']}{RESET} {chunk.content}", "cyan")
            return

        # 错误事件
        if event == "error":
            print()
            color_print(f"  {COLORS['red']}{SYMBOLS['cross']}{RESET} {chunk.content}", "red")
            return

        # 思考事件
        if event == "thinking":
            print()
            color_print(f"  {COLORS['yellow']}💭 Thinking{RESET}")
            draw_divider("·", 40, "dim")
            for line in chunk.content.split("\n"):
                if line.strip():
                    color_print(f"    {line}", "dim")
            return

        # 工具调用事件
        if event == "tool_call":
            self.tool_count += 1
            self.last_tool = chunk.tool_name
            print()
            color_print(
                f"  {COLORS['yellow']}{make_tag('TOOL', 'yellow')}{RESET} "
                f"{COLORS['bold']}{chunk.tool_name}{RESET}"
            )
            if chunk.tool_args:
                args_str = json.dumps(chunk.tool_args, ensure_ascii=False)
                if len(args_str) > 200:
                    args_str = args_str[:200] + "..."
                color_print(f"  {COLORS['dim']}  Args: {args_str}{RESET}")
            color_print(f"  {COLORS['dim']}  ⏳ Running...{RESET}")
            return

        # 工具结果事件
        if event == "tool_result":
            result = chunk.tool_result or ""
            result_show = result[:300] + "..." if len(result) > 300 else result
            is_error = '"error"' in result_show.lower() or "Error" in result_show

            if is_error:
                color_print(f"  {COLORS['red']}{SYMBOLS['cross']} Error{RESET}")
                for line in result_show.split("\n")[:5]:
                    if line.strip():
                        color_print(f"    {line}", "red")
            else:
                color_print(f"  {COLORS['green']}{SYMBOLS['check']} Done{RESET}")
                for line in result_show.split("\n")[:3]:
                    if line.strip():
                        color_print(f"    {COLORS['dim']}{line}{RESET}")
                if len(result) > 300:
                    color_print(f"    {COLORS['dim']}... ({len(result)} chars){RESET}")
            return

        # 普通文本内容 — 只缓冲，不直接打印（结束后统一渲染 markdown）
        if chunk.content:
            self.buffer.add_content(chunk.content)

        # 旧格式兼容：直接在 chunk 上的 tool_calls
        if chunk.tool_calls:
            for tc in chunk.tool_calls:
                self.buffer.add_tool_call(tc.name, tc.arguments)
                self.tool_count += 1
                self.last_tool = tc.name

    # ── 命令处理 ──────────────────────────────────────────────

    async def process_command(self, command):
        """处理斜杠命令"""
        cmd = command.strip().lower()

        if cmd in ["/help", "/h", "/?"]:
            self.show_help()
        elif cmd in ["/quit", "/q", "/exit"]:
            color_print(f"  {SYMBOLS['check']} Bye!", "green")
            self.running = False
        elif cmd in ["/clear", "/c"]:
            os.system("cls" if os.name == "nt" else "clear")
            self.show_banner()
        elif cmd == "/config":
            self.show_config()
        elif cmd == "/tools":
            self.show_tools()
        elif cmd == "/skills":
            self.show_skills()
        elif cmd == "/memory":
            self.show_memory()
        elif cmd == "/status":
            self.show_status()
        elif cmd == "/history":
            self.show_history()
        elif cmd == "/reset":
            self.msg_count = 0
            self.tool_count = 0
            color_print(f"  {SYMBOLS['check']} Counters reset", "green")
        elif cmd == "/new":
            session = self.session_mgr.create_session("New")
            color_print(f"  {SYMBOLS['check']} New session: {session.id}", "green")
        elif cmd == "/save":
            if self.session_mgr.current_session_id:
                self.session_mgr._save_session(
                    self.session_mgr.get_session(self.session_mgr.current_session_id)
                )
                color_print(f"  {SYMBOLS['check']} Saved", "green")
        elif cmd == "/undo":
            color_print(f"  {SYMBOLS['cross']} Not yet", "yellow")
        elif cmd == "/checkpoints":
            color_print(f"  {SYMBOLS['cross']} Not yet", "yellow")
        elif cmd == "/session":
            await self.switch_session()
        elif cmd.startswith("/delete"):
            await self.delete_session(cmd)
        else:
            color_print(f"  {SYMBOLS['cross']} Unknown: {cmd}", "red")

    # ── 用户输入处理 ──────────────────────────────────────────

    async def handle_input(self, text):
        """处理用户输入"""
        text = text.strip()
        if not text:
            return

        # 斜杠命令
        if text.startswith("/"):
            if text.lower() in ["/quit", "/q", "/exit"]:
                color_print(f"  {SYMBOLS['check']} Bye!", "green")
                self.running = False
                return
            await self.process_command(text)
            return

        # 普通消息
        print()
        color_print(
            f"  {COLORS['green']}{make_tag('YOU', 'green')}{RESET} {text}"
        )
        draw_divider("·", 50, "dim")
        self.msg_count += 1
        self.buffer.clear()

        try:
            await self.agent.run(text, stream_callback=self.handle_stream_chunk)

            # 渲染收集的 markdown 内容
            print()
            if self.buffer.text.strip():
                rendered = render_markdown_ansi(self.buffer.text)
                for line in rendered.split("\n"):
                    color_print(line)

            # 显示 token 用量
            if self.agent.last_usage:
                usage = self.agent.last_usage
                prompt_tokens = usage.get("prompt_tokens", 0)
                completion_tokens = usage.get("completion_tokens", 0)
                total_tokens = usage.get("total_tokens", 0)
                color_print(
                    f"  {COLORS['dim']}📊 Tokens: {prompt_tokens} in + "
                    f"{completion_tokens} out = {total_tokens} total{RESET}"
                )
        except Exception as e:
            logger.error(f"Agent run error: {e}", exc_info=True)
            color_print(f"  {SYMBOLS['cross']} Error: {e}", "red")

        print()
        self.show_status()

    # ── 主循环 ────────────────────────────────────────────────

    async def run(self):
        """启动 TUI 主循环"""
        self.show_banner()
        color_print(f"  {COLORS['cyan']}⏳ Initializing...{RESET}")
        await self.agent.initialize()

        # 确保有活跃会话
        if not self.session_mgr.current_session_id:
            self.session_mgr.create_session("New")

        # 显示就绪信息
        from plugins import get_plugin_manager

        plugin_mgr = get_plugin_manager()
        print()
        draw_box("Ready", [
            f"{COLORS['cyan']}Provider:{RESET} {COLORS['white']}{self.config.llm.provider}{RESET}",
            f"{COLORS['cyan']}Model:{RESET}    {COLORS['white']}{self.config.llm.model}{RESET}",
            f"{COLORS['cyan']}Skills:{RESET}   {COLORS['white']}{len(plugin_mgr.list_skills())}{RESET}",
            f"{COLORS['cyan']}Session:{RESET}  {COLORS['dim']}{self.session_mgr.current_session_id}{RESET}",
        ], self._width)
        print()
        self.show_status()

        # 创建 prompt_toolkit 会话
        prompt_session = PromptSession(
            history=FileHistory(".rabbit_tui_history"),
            completer=CommandCompleter(COMMANDS),
            style=PROMPT_STYLE,
        )

        with patch_stdout():
            while self.running:
                try:
                    text = await prompt_session.prompt_async(
                        HTML('<prompt>rabbit> </prompt>')
                    )
                    await self.handle_input(text)
                except KeyboardInterrupt:
                    print()
                    color_print("  Ctrl+C", "yellow")
                except EOFError:
                    print()
                    color_print(f"  {SYMBOLS['check']} Bye!", "green")
                    break
                except Exception as e:
                    logger.error(f"TUI error: {e}", exc_info=True)
                    color_print(f"  {SYMBOLS['cross']} {e}", "red")

        await self.agent.close()


async def run_tui_mode(config, command=None):
    """TUI 模式入口"""
    tui = RabbitTUI(config)
    if command:
        await tui.agent.initialize()
        await tui.handle_input(command)
    else:
        await tui.run()
