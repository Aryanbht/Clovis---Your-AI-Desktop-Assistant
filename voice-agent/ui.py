import time
from datetime import datetime
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.table import Table
from rich.align import Align
from rich.spinner import Spinner
from rich.live import Live
from rich.columns import Columns
from rich import box
from rich.style import Style

console = Console()

def show_banner():
    ascii_art = """
  ██████╗ ██╗      ██████╗ ██╗   ██╗ ██╗ ███████╗
 ██╔════╝ ██║     ██╔═══██╗██║   ██║ ██║ ██╔════╝
 ██║      ██║     ██║   ██║╚██╗ ██╔╝ ██║ ███████╗
 ██║      ██║     ██║   ██║ ╚████╔╝  ██║ ╚════██║
 ╚██████╗ ███████╗╚██████╔╝  ╚██╔╝   ██║ ███████║
  ╚═════╝ ╚══════╝ ╚═════╝    ╚═╝    ╚═╝ ╚══════╝
                                                 
           Your AI Desktop Assistant             
                v1.0.0 · Offline                 
"""
    panel = Panel(
        Align.center(ascii_art),
        border_style="bright_cyan",
        subtitle="[dim white]Powered by Ollama + Whisper[/dim white]",
        subtitle_align="center",
        expand=False
    )
    # Center the panel in the terminal
    console.print(Align.center(panel))

def show_menu() -> str:
    table = Table(
        box=box.ROUNDED, 
        show_header=True,
        title="How would you like to interact today?",
        title_style="white",
        title_justify="left"
    )
    table.add_column("#", style="bright_cyan", justify="center")
    table.add_column("Mode", style="white bold")
    table.add_column("Description", style="dim white")
    
    table.add_row("1", "💬 Chat Mode", "Type commands")
    table.add_row("2", "🎙  Voice Mode", 'Say "Clovis"')
    table.add_row("3", "⚡ Voice Direct", "Speak immediately")
    table.add_row("4", "🔀 Hybrid Mode", "Type OR speak")
    table.add_row("5", "✖  Exit", "")
    
    console.print(table)
    choice = console.input("[bright_cyan]Enter choice [1-5]: [/bright_cyan]")
    return choice.strip()
    
def show_status_panel(model: str, whisper: str, wake_word: str, mode: str, is_running: bool):
    text = Text()
    text.append("Model    ", style="dim cyan")
    text.append(f"{model}\n", style="white")
    text.append("Whisper  ", style="dim cyan")
    text.append(f"{whisper}\n", style="white")
    text.append("Wake     ", style="dim cyan")
    text.append(f"'{wake_word}'\n", style="white")
    text.append("Mode     ", style="dim cyan")
    text.append(f"{mode}", style="white")
    
    panel = Panel(
        text,
        title="Clovis is ready",
        title_align="left",
        border_style="green" if is_running else "yellow",
        expand=False
    )
    console.print(panel)

def show_ollama_status(is_running: bool):
    if is_running:
        console.print("[green]●[/green] Ollama running — LLM features available")
    else:
        console.print("[yellow]●[/yellow] Ollama offline — Fast path only")
    console.print()

def log_intent(path: str, intent: str, params: dict):
    ts = datetime.now().strftime("%H:%M:%S")
    
    if path.upper() == "FAST":
        path_styled = "[cyan][FAST][/cyan]"
    elif path.upper() == "LLM":
        path_styled = "[magenta][LLM][/magenta]"
    else:
        path_styled = f"[red][{path}][/red]"
        
    params_str = " ".join([f"{k}={v}" for k, v in params.items()])
    
    console.print(f"[dim gray]{ts}[/dim gray] {path_styled} [bold]{intent}[/bold] · [dim white]{params_str}[/dim white]")

_listening_live = None

def show_listening():
    global _listening_live
    if _listening_live:
        return
    text = Text("● Listening...", style="bright_green")
    text.stylize("blink", 0, 1)
    _listening_live = Live(text, console=console, refresh_per_second=4, transient=True)
    _listening_live.start()

def stop_listening():
    global _listening_live
    if _listening_live:
        _listening_live.stop()
        _listening_live = None

_thinking_live = None

def show_thinking():
    global _thinking_live
    if _thinking_live:
        return
    spinner = Spinner("dots", text="Thinking...", style="bright_yellow")
    _thinking_live = Live(spinner, console=console, refresh_per_second=10, transient=True)
    _thinking_live.start()

def stop_thinking():
    global _thinking_live
    if _thinking_live:
        _thinking_live.stop()
        _thinking_live = None

def show_response(text: str):
    if not text:
        return
    panel = Panel(
        text,
        title="Clovis",
        title_align="left",
        border_style="dim cyan",
        style="white",
        expand=False
    )
    console.print(panel)

def show_error(message: str):
    panel = Panel(
        message,
        title="Error",
        title_align="left",
        border_style="red",
        style="white",
        expand=False
    )
    console.print(panel)

def show_farewell():
    text = Text("Goodbye, Aryan. See you.", justify="center", style="dim white")
    panel = Panel(
        text,
        border_style="dim cyan",
        expand=False
    )
    console.print(Align.center(panel))
