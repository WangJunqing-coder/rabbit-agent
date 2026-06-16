#!/usr/bin/env python3
import asyncio, json, os, sys
from datetime import datetime
from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.styles import Style
from prompt_toolkit.formatted_text import HTML, ANSI as ANSI_TEXT
from prompt_toolkit.patch_stdout import patch_stdout
from prompt_toolkit import print_formatted_text
from config import Config
from agent import Agent
from sessions import get_session_manager

# ── ANSI 颜色定义 ──────────────────────────────────────────────
_C={
    "red":"\033[91m","green":"\033[92m","yellow":"\033[93m",
    "blue":"\033[94m","magenta":"\033[95m","cyan":"\033[96m",
    "white":"\033[97m","dim":"\033[90m","bold":"\033[1m",
    "reset":"\033[0m","bg_blue":"\033[44m","bg_green":"\033[42m",
    "bg_yellow":"\033[43m","bg_red":"\033[41m","bg_cyan":"\033[46m",
    "underline":"\033[4m","italic":"\033[3m",
}
_R="\033[0m"

def cprint(text, color="white"):
    c=_C.get(color,"")
    try: print_formatted_text(ANSI_TEXT(f"{c}{text}{_R}"))
    except: print(f"{c}{text}{_R}")

def cprint_inline(text, color="white"):
    c=_C.get(color,"")
    try: print_formatted_text(ANSI_TEXT(f"{c}{text}{_R}"), end="")
    except: print(f"{c}{text}{_R}", end="")

def cprint_multi(*parts):
    """多色打印: cprint_multi(('text','color'), ('text2','color2'))"""
    line=""
    for text,color in parts:
        c=_C.get(color,"")
        line+=f"{c}{text}{_R}"
    try: print_formatted_text(ANSI_TEXT(line))
    except: print(line)

# ── 符号定义 ──────────────────────────────────────────────────
S={
    "box_h":"─","box_v":"│","box_tl":"┌","box_tr":"┐",
    "box_bl":"└","box_br":"┘","box_ml":"├","box_mr":"┤",
    "dot":"●","arrow":"▸","check":"✓","cross":"✗",
    "star":"★","bullet":"◆","line":"━",
}

# ── 命令列表 ──────────────────────────────────────────────────
CMDS={
    "/help":"Show commands","/quit":"Exit",
    "/clear":"Clear screen","/config":"Show config",
    "/tools":"List tools","/skills":"List skills",
    "/memory":"Memory stats","/status":"Show status",
    "/new":"New session","/save":"Save session",
    "/history":"Show history","/reset":"Reset counters",
    "/session":"Switch session","/delete":"Delete session",
}

PT=Style.from_dict({
    "prompt":"ansicyan bold",
    "prompt.user":"ansigreen bold",
    "prompt.arrow":"ansiyellow",
})

# ── 补全器 ────────────────────────────────────────────────────
class CC(Completer):
    def __init__(s,c):s.c=c
    def get_completions(s,d,e):
        t=d.text_before_cursor
        if t.startswith("/"):
            for k,v in s.c.items():
                if k.startswith(t):yield Completion(k,start_position=-len(t),display_meta=v)

# ── 流式缓冲 ──────────────────────────────────────────────────
class SB:
    def __init__(s):s.txt="";s.tl=[]
    def clear(s):s.txt="";s.tl=[]
    def add(s,c):s.txt+=c
    def tool(s,n,a):s.tl.append((n,a))

# ── 辅助函数 ──────────────────────────────────────────────────
def _box(title, lines, width=56):
    """绘制带标题的盒子"""
    cprint(f"  {_C['cyan']}{S['box_tl']}{S['box_h']*2} {_C['bold']}{title}{_R}{_C['cyan']}{S['box_h']*(width-len(title)-4)}{S['box_tr']}{_R}")
    for line in lines:
        cprint(f"  {_C['cyan']}{S['box_v']}{_R} {line}{' '*(width-len(line)-3)}{_C['cyan']}{S['box_v']}{_R}")
    cprint(f"  {_C['cyan']}{S['box_bl']}{S['box_h']*width}{S['box_br']}{_R}")

def _divider(char="─", width=56, color="dim"):
    cprint(f"  {_C[color]}{char*width}{_R}")

def _tag(text, bg="cyan"):
    """生成标签样式"""
    bg_c=_C.get(f"bg_{bg}","")
    return f"{bg_c}{_C['bold']} {text} {_R}"

# ── 主类 ──────────────────────────────────────────────────────
class RTUI:
    def __init__(s,cfg):
        s.cfg=cfg;s.a=Agent(cfg);s.sm=get_session_manager()
        s.tc=0;s.mc=0;s.buf=SB();s.R=True;s.t0=datetime.now();s.lt=""
        s._width=56

    def el(s):
        sc=int((datetime.now()-s.t0).total_seconds())
        if sc<60:return f"{sc}s"
        return f"{sc//60}m{sc%60}s"

    def _ctx_bar(s):
        from config import get_context_window
        model=s.cfg.llm.model
        max_tokens=s.cfg.llm.context_window if s.cfg.llm.context_window>0 else get_context_window(model)
        used_tokens=0
        usage=s.a.last_usage if s.a else {}
        if usage and usage.get("prompt_tokens"):
            used_tokens=usage["prompt_tokens"]
        elif s.a and s.a.context:
            total_chars=sum(len(m.content or "") for m in s.a.context.messages)
            used_tokens=total_chars//3
        pct=min(used_tokens/max_tokens,1.0) if max_tokens>0 else 0
        bar_len=15
        filled=int(pct*bar_len)
        bar=f"{_C['green']}{'█'*filled}{_C['dim']}{'░'*(bar_len-filled)}{_R}"
        if pct>=0.8:bar=f"{_C['red']}{'█'*filled}{_C['dim']}{'░'*(bar_len-filled)}{_R}"
        elif pct>=0.6:bar=f"{_C['yellow']}{'█'*filled}{_C['dim']}{'░'*(bar_len-filled)}{_R}"
        def fmt(n):
            if n>=1000:return f"{n/1000:.1f}K"
            return str(n)
        warn=""
        if pct>=0.9:warn=f" {_C['red']}⚠{_R}"
        elif pct>=0.7:warn=f" {_C['yellow']}△{_R}"
        return f"{bar} {fmt(used_tokens)}/{fmt(max_tokens)} ({pct*100:.0f}%){warn}"

    def ban(s):
        w=s._width
        print()
        logo=[
            f"{_C['cyan']}{_C['bold']}  ╦═╗╔═╗╔═╗╔╦╗╦╔╦╗╔═╗  ╔═╗╔═╗╔╦╗╔═╗╦═╗{_R}",
            f"{_C['cyan']}{_C['bold']}  ╠╦╝║╣ ╚═╗ ║ ║║║║║ ║  ║ ╦║╣  ║ ║╣ ╠╦╝{_R}",
            f"{_C['cyan']}  ╩╚═╚═╝╚═╝ ╩ ╩╩ ╩╚═╝  ╚═╝╚═╝ ╩ ╚═╝╩╚═{_R}",
        ]
        for line in logo:cprint(line)
        print()
        _box("Info",[
            f"{_tag('v1.0')} {_C['white']}Rabbit Agent TUI{_R}",
            f"{_tag('cmd')} {_C['dim']}Type /help for commands{_R}",
            f"{_tag('exit')} {_C['dim']}/quit or Ctrl+D{_R}",
        ],w)
        print()

    def sta(s):
        w=s._width
        tc=f"{_C['yellow']}{s.tc}{_R}"
        mc=f"{_C['cyan']}{s.mc}{_R}"
        tm=f"{_C['green']}{s.el()}{_R}"
        ctx=s._ctx_bar()
        line=f"  {_C['dim']}Tools:{_R} {tc} {_C['dim']}│{_R} {_C['dim']}Msgs:{_R} {mc} {_C['dim']}│{_R} {_C['dim']}Time:{_R} {tm}"
        cprint(line)
        cprint(f"  {_C['dim']}Context:{_R} {ctx}")
        _divider("─",w)

    def hlp(s):
        w=s._width
        print()
        lines=[]
        for k,v in CMDS.items():
            lines.append(f"{_C['cyan']}{k:<14}{_R} {_C['white']}{v}{_R}")
        _box("Commands",lines,w)
        print()

    def cfg(s):
        w=s._width
        print()
        _box("Config",[
            f"{_C['cyan']}Provider:{_R} {_C['white']}{s.cfg.llm.provider}{_R}",
            f"{_C['cyan']}Model:{_R}    {_C['white']}{s.cfg.llm.model}{_R}",
            f"{_C['cyan']}API Base:{_R} {_C['dim']}{s.cfg.llm.api_base}{_R}",
            f"{_C['cyan']}Max Tokens:{_R} {_C['white']}{s.cfg.llm.max_tokens}{_R}",
        ],w)
        print()

    def tls(s):
        from tools.registry import registry
        w=s._width
        print()
        lines=[]
        for i,tl in enumerate(registry.list_tools(),1):
            desc=tl.description[:35]+"..." if len(tl.description)>35 else tl.description
            lines.append(f"{_C['yellow']}{i:>2}.{_R} {_C['white']}{tl.name:<16}{_R} {_C['dim']}{desc}{_R}")
        _box(f"Tools ({len(lines)})",lines,w)
        print()

    def sks(s):
        from plugins import get_plugin_manager
        w=s._width
        skills=get_plugin_manager().list_skills()
        print()
        lines=[]
        for i,sk in enumerate(skills,1):
            lines.append(f"{_C['yellow']}{i:>2}.{_R} {_C['white']}{sk['name']}{_R}")
        _box(f"Skills ({len(lines)})",lines,w)
        print()

    def mem(s):
        from memory import MemoryManager
        w=s._width
        st=MemoryManager().store.get_stats()
        print()
        lines=[]
        icons={"conversation":"💬","preference":"⚙️","project":"📁","knowledge":"📚"}
        for c in ["conversation","preference","project","knowledge"]:
            icon=icons.get(c,"•")
            count=st.get(c,0)
            lines.append(f"{icon} {_C['cyan']}{c:<14}{_R} {_C['white']}{count}{_R}")
        _box("Memory",lines,w)
        print()

    def hist(s):
        if not s.a.context:
            cprint("  No history","dim");return
        ms=[m for m in s.a.context.messages if m.role in ["user","assistant"]]
        w=s._width
        print()
        lines=[]
        for m in ms[-6:]:
            if m.role=="user":
                txt=m.content[:45]+"..." if len(m.content)>45 else m.content
                lines.append(f"{_C['green']}You{_R} {_C['dim']}▸{_R} {txt}")
            else:
                txt=m.content[:45]+"..." if len(m.content)>45 else m.content
                lines.append(f"{_C['blue']}AI{_R}  {_C['dim']}▸{_R} {txt}")
        _box(f"History ({len(ms)} msgs)",lines,w)
        print()

    async def ses(s):
        sessions=s.sm.list_sessions()
        if not sessions:
            print();cprint("  No sessions","dim");print();return
        cur_idx=0
        for i,sess in enumerate(sessions):
            if sess.id==s.sm.current_session_id:cur_idx=i;break
        idx=await s._pick_arrow(sessions,cur_idx,header="  Sessions: ↑↓ select, Enter switch, Esc cancel")
        if idx is None:cprint("  Cancelled","dim");print();return
        target=sessions[idx]
        s.sm.switch_session(target.id)
        cprint(f"  {S['check']} Switched to: {target.title}","green");print()

    async def del_s(s,cmd):
        sessions=s.sm.list_sessions()
        if not sessions:
            print();cprint("  No sessions to delete","dim");print();return
        cur_idx=0
        for i,sess in enumerate(sessions):
            if sess.id==s.sm.current_session_id:cur_idx=i;break
        idx=await s._pick_arrow(sessions,cur_idx,header="  Delete: ↑↓ select, Enter delete, Esc cancel")
        if idx is None:cprint("  Cancelled","dim");print();return
        target=sessions[idx]
        if s.sm.delete_session(target.id):
            cprint(f"  {S['check']} Deleted: {target.title}","green")
            new=s.sm.get_current_session()
            if new:cprint(f"  {S['arrow']} Current: {new.title}","cyan")
            else:cprint("  No sessions left. Use /new","dim")
        else:cprint(f"  {S['cross']} Delete failed","red")
        print()

    async def _pick_arrow(s,sessions,cur_idx=0,header=""):
        from prompt_toolkit import Application
        from prompt_toolkit.key_binding import KeyBindings
        from prompt_toolkit.layout import Layout
        from prompt_toolkit.layout.containers import HSplit, Window
        from prompt_toolkit.layout.controls import FormattedTextControl
        from prompt_toolkit.formatted_text import FormattedText
        selected=[cur_idx];result=[None]
        def get_text():
            lines=[("class:header",header+"\n"),("","  "+"─"*50+"\n")]
            for i,sess in enumerate(sessions):
                marker=S["arrow"] if i==selected[0] else " "
                msg_count=len(sess.messages)
                title=sess.title[:30]+"..." if len(sess.title)>30 else sess.title
                line=f"  {marker} [{sess.id}] {title} ({msg_count} msgs)"
                if i==selected[0]:lines.append(("class:selected",line+"\n"))
                else:lines.append(("",line+"\n"))
            return FormattedText(lines)
        control=FormattedTextControl(get_text);body=Window(content=control)
        bindings=KeyBindings()
        @bindings.add("up")
        def _(e):selected[0]=(selected[0]-1)%len(sessions)
        @bindings.add("down")
        def _(e):selected[0]=(selected[0]+1)%len(sessions)
        @bindings.add("enter")
        def _(e):result[0]=selected[0];e.app.exit()
        @bindings.add("escape")
        def _(e):e.app.exit()
        @bindings.add("q")
        def _(e):e.app.exit()
        app=Application(layout=Layout(body),key_bindings=bindings,
            style=Style.from_dict({"selected":"ansicyan bold reverse","header":"ansiyellow"}),
            full_screen=False)
        await app.run_async()
        return result[0]

    # ── 流式输出处理 ──────────────────────────────────────────
    async def sh(self,chunk):
        evt=getattr(chunk,'event_type','')
        # 状态
        if evt=='status':
            print()
            cprint(f"  {_C['cyan']}{S['dot']}{_R} {chunk.content}","cyan")
            return
        # 错误
        if evt=='error':
            print()
            cprint(f"  {_C['red']}{S['cross']}{_R} {chunk.content}","red")
            return
        # 思考
        if evt=='thinking':
            print()
            cprint(f"  {_C['yellow']}💭 Thinking{_R}")
            _divider("·",40,"dim")
            for line in chunk.content.split('\n'):
                if line.strip():cprint(f"    {line}","dim")
            return
        # 工具调用
        if evt=='tool_call':
            self.tc+=1;self.lt=chunk.tool_name
            print()
            cprint(f"  {_C['yellow']}{_tag('TOOL','yellow')}{_R} {_C['bold']}{chunk.tool_name}{_R}")
            if chunk.tool_args:
                args_str=json.dumps(chunk.tool_args,ensure_ascii=False)
                if len(args_str)>200:args_str=args_str[:200]+"..."
                cprint(f"  {_C['dim']}  Args: {args_str}{_R}")
            cprint(f"  {_C['dim']}  ⏳ Running...{_R}")
            return
        # 工具结果
        if evt=='tool_result':
            result=chunk.tool_result or ''
            if len(result)>300:result_show=result[:300]+"..."
            else:result_show=result
            is_error='"error"' in result_show.lower() or 'Error' in result_show
            if is_error:
                cprint(f"  {_C['red']}{S['cross']} Error{_R}")
                for line in result_show.split('\n')[:5]:
                    if line.strip():cprint(f"    {line}","red")
            else:
                cprint(f"  {_C['green']}{S['check']} Done{_R}")
                for line in result_show.split('\n')[:3]:
                    if line.strip():cprint(f"    {_C['dim']}{line}{_R}")
                if len(result)>300:cprint(f"    {_C['dim']}... ({len(result)} chars){_R}")
            return
        # 普通内容
        if chunk.content:
            self.buf.add(chunk.content);cprint_inline(chunk.content)
        # 旧格式兼容
        if chunk.tool_calls:
            for tc in chunk.tool_calls:
                self.buf.tool(tc.name,tc.arguments);self.tc+=1;self.lt=tc.name

    # ── 命令处理 ──────────────────────────────────────────────
    async def proc(self,c):
        c=c.strip().lower()
        if c in ["/help","/h","/?"]:self.hlp()
        elif c in ["/quit","/q","/exit"]:
            cprint(f"  {S['check']} Bye!","green");self.R=False
        elif c in ["/clear","/c"]:
            os.system("cls" if os.name=="nt" else "clear");self.ban()
        elif c=="/config":self.cfg()
        elif c=="/tools":self.tls()
        elif c=="/skills":self.sks()
        elif c=="/memory":self.mem()
        elif c=="/status":self.sta()
        elif c=="/history":self.hist()
        elif c=="/reset":
            self.mc=0;self.tc=0
            cprint(f"  {S['check']} Counters reset","green")
        elif c=="/new":
            sid=self.sm.create_session("New")
            cprint(f"  {S['check']} New session: {sid.id}","green")
        elif c=="/save":
            if self.sm.current_session_id:
                self.sm._save_session(self.sm.get_session(self.sm.current_session_id))
                cprint(f"  {S['check']} Saved","green")
        elif c=="/undo":cprint(f"  {S['cross']} Not yet","yellow")
        elif c=="/checkpoints":cprint(f"  {S['cross']} Not yet","yellow")
        elif c=="/session":await self.ses()
        elif c.startswith("/delete"):await self.del_s(c)
        else:cprint(f"  {S['cross']} Unknown: {c}","red")

    # ── 输入处理 ──────────────────────────────────────────────
    async def inp(self,text):
        text=text.strip()
        if not text:return
        if text.startswith("/"):
            if text.lower() in ["/quit","/q","/exit"]:
                cprint(f"  {S['check']} Bye!","green");self.R=False;return
            await self.proc(text);return
        # 用户输入
        print()
        cprint(f"  {_C['green']}{_tag('YOU','green')}{_R} {text}")
        _divider("·",50,"dim")
        self.mc+=1;self.buf.clear()
        try:
            await self.a.run(text,stream_callback=self.sh)
            print()
            if self.a.last_usage:
                u=self.a.last_usage
                pt=u.get('prompt_tokens',0);ct=u.get('completion_tokens',0);tt=u.get('total_tokens',0)
                cprint(f"  {_C['dim']}📊 Tokens: {pt} in + {ct} out = {tt} total{_R}")
        except Exception as e:cprint(f"  {S['cross']} Error: {e}","red")
        print();self.sta()

    # ── 主循环 ────────────────────────────────────────────────
    async def run(self):
        self.ban()
        cprint(f"  {_C['cyan']}⏳ Initializing...{_R}")
        await self.a.initialize()
        if not self.sm.current_session_id:self.sm.create_session("New")
        from plugins import get_plugin_manager
        pm=get_plugin_manager()
        print()
        _box("Ready",[
            f"{_C['cyan']}Provider:{_R} {_C['white']}{self.cfg.llm.provider}{_R}",
            f"{_C['cyan']}Model:{_R}    {_C['white']}{self.cfg.llm.model}{_R}",
            f"{_C['cyan']}Skills:{_R}   {_C['white']}{len(pm.list_skills())}{_R}",
            f"{_C['cyan']}Session:{_R}  {_C['dim']}{self.sm.current_session_id}{_R}",
        ],self._width)
        print();self.sta()
        sess=PromptSession(
            history=FileHistory(".rabbit_tui_history"),
            completer=CC(CMDS),style=PT
        )
        with patch_stdout():
            while self.R:
                try:
                    text=await sess.prompt_async(HTML("<prompt>rabbit> </prompt>"))
                    await self.inp(text)
                except KeyboardInterrupt:
                    print();cprint("  Ctrl+C","yellow")
                except EOFError:
                    print();cprint(f"  {S['check']} Bye!","green");break
                except Exception as e:cprint(f"  {S['cross']} {e}","red")
        await self.a.close()

async def run_tui_mode(config,command=None):
    tui=RTUI(config)
    if command:
        await tui.a.initialize();await tui.inp(command)
    else:await tui.run()
