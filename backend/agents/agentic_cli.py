"""
Agentic CLI Mode — GitHub Copilot-style autonomous coding agent.

Uses Claude's tool use API to read files, write files, run commands,
and iterate to complete coding tasks in a real working directory.
"""
import asyncio
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

import anthropic
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.syntax import Syntax

from agents.tools import TOOL_DEFINITIONS, ToolExecutor
from llm.client import LLMClient
from prompts.loader import PromptCache

logger = logging.getLogger(__name__)
console = Console()

SYSTEM_PROMPT = """You are an expert software engineer and coding assistant — similar to GitHub Copilot's agent mode.
You have access to tools that let you read files, write files, run commands, and search code in a real codebase.

Your job is to complete the user's coding task autonomously:
1. First understand the codebase by reading relevant files
2. Plan your changes
3. Implement the changes using write_file
4. Verify your work by running tests or the relevant command
5. Iterate if tests fail

Rules:
- Always read files before modifying them
- Run tests after making changes to verify correctness
- Make minimal, focused changes — don't refactor unrelated code
- Follow existing code style and patterns
- When done, provide a clear summary of what you changed and why
- If you encounter an error you cannot fix, explain what the issue is

You have a maximum of {max_turns} tool-use turns before you must conclude.
"""

MAX_TURNS_DEFAULT = 20


@dataclass
class AgentResult:
    task: str
    working_dir: str
    files_written: list[str] = field(default_factory=list)
    files_read: list[str] = field(default_factory=list)
    commands_run: list[str] = field(default_factory=list)
    turns_used: int = 0
    total_tokens: int = 0
    summary: str = ""
    success: bool = True


class AgenticCLI:
    """
    Agentic CLI: uses Claude tool use to autonomously complete coding tasks.

    Usage:
        agent = AgenticCLI()
        result = await agent.run(
            task="Add input validation to auth/login.py",
            working_dir=Path("./my-project"),
        )
    """

    def __init__(self, max_turns: int = MAX_TURNS_DEFAULT):
        self._llm = LLMClient()
        self._max_turns = max_turns

    async def run(
        self,
        task: str,
        working_dir: Path,
        on_tool_call: Optional[Callable] = None,
        on_text: Optional[Callable] = None,
    ) -> AgentResult:
        """
        Run the agentic loop for the given task.

        Args:
            task: Natural language description of what to do
            working_dir: Root directory to work in
            on_tool_call: Optional callback(tool_name, tool_input, result) for UI updates
            on_text: Optional callback(text) for streaming text display
        """
        working_dir = working_dir.resolve()
        executor = ToolExecutor(working_dir)

        messages = [{"role": "user", "content": task}]
        system = PromptCache.get("agentic_cli_system", SYSTEM_PROMPT).format(
            max_turns=self._max_turns
        )

        total_tokens = 0
        turns = 0
        final_summary = ""
        commands_run = []

        console.print(
            Panel(
                f"[bold cyan]Task:[/bold cyan] {task}\n"
                f"[dim]Working directory:[/dim] {working_dir}",
                title="GBADS Agent",
                border_style="cyan",
            )
        )

        while turns < self._max_turns:
            turns += 1

            response, p_tokens, c_tokens = await self._llm.complete_with_tools(
                system=system,
                messages=messages,
                tools=TOOL_DEFINITIONS,
                max_tokens=4096,
            )
            total_tokens += p_tokens + c_tokens

            # Collect text and tool_use blocks from response
            text_parts = []
            tool_calls = []
            for block in response.content:
                if block.type == "text":
                    text_parts.append(block.text)
                elif block.type == "tool_use":
                    tool_calls.append(block)

            # Display any text output
            if text_parts:
                combined_text = "\n".join(text_parts)
                if on_text:
                    on_text(combined_text)
                else:
                    console.print(Markdown(combined_text))
                final_summary = combined_text

            # If no tool calls, Claude is done
            if response.stop_reason == "end_turn" or not tool_calls:
                break

            # Add assistant message to conversation
            messages.append({"role": "assistant", "content": response.content})

            # Execute each tool call and collect results
            tool_results = []
            for tool_call in tool_calls:
                tool_name = tool_call.name
                tool_input = tool_call.input

                # Display tool call
                _display_tool_call(tool_name, tool_input)

                # Execute
                result = executor.execute(tool_name, tool_input)

                # Track commands
                if tool_name == "run_command":
                    commands_run.append(tool_input.get("command", ""))

                # Display result (truncated)
                _display_tool_result(tool_name, result)

                if on_tool_call:
                    on_tool_call(tool_name, tool_input, result)

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_call.id,
                    "content": result,
                })

            # Add tool results to conversation
            messages.append({"role": "user", "content": tool_results})

        # Final summary
        _display_summary(executor, commands_run, turns, total_tokens)

        return AgentResult(
            task=task,
            working_dir=str(working_dir),
            files_written=list(set(executor.files_written)),
            files_read=list(set(executor.files_read)),
            commands_run=commands_run,
            turns_used=turns,
            total_tokens=total_tokens,
            summary=final_summary,
            success=True,
        )

    async def run_interactive(self, working_dir: Path) -> None:
        """
        Interactive REPL mode: accept tasks in a loop until user quits.
        """
        working_dir = working_dir.resolve()
        console.print(
            Panel(
                f"[bold cyan]GBADS Agent — Interactive Mode[/bold cyan]\n"
                f"[dim]Working directory:[/dim] {working_dir}\n"
                "[dim]Type your task and press Enter. Type 'quit' or 'exit' to stop.[/dim]",
                border_style="cyan",
            )
        )

        while True:
            try:
                task = console.input("\n[bold cyan]Task>[/bold cyan] ").strip()
            except (EOFError, KeyboardInterrupt):
                console.print("\n[yellow]Bye![/yellow]")
                break

            if task.lower() in {"quit", "exit", "q"}:
                console.print("[yellow]Bye![/yellow]")
                break

            if not task:
                continue

            await self.run(task=task, working_dir=working_dir)


# ── Display helpers ────────────────────────────────────────────────────────────

def _display_tool_call(tool_name: str, tool_input: dict) -> None:
    icons = {
        "read_file": "📖",
        "write_file": "✏️ ",
        "list_files": "📁",
        "run_command": "⚡",
        "search_code": "🔍",
    }
    icon = icons.get(tool_name, "🔧")

    if tool_name == "read_file":
        console.print(f"  {icon} [dim]read_file:[/dim] {tool_input.get('path')}")
    elif tool_name == "write_file":
        path = tool_input.get('path')
        lines = len(tool_input.get('content', '').splitlines())
        console.print(f"  {icon} [dim]write_file:[/dim] {path} [dim]({lines} lines)[/dim]")
    elif tool_name == "list_files":
        console.print(f"  {icon} [dim]list_files:[/dim] {tool_input.get('pattern')}")
    elif tool_name == "run_command":
        cmd = tool_input.get('command', '')
        console.print(f"  {icon} [dim]run:[/dim] [bold]{cmd}[/bold]")
    elif tool_name == "search_code":
        console.print(f"  {icon} [dim]search:[/dim] {tool_input.get('pattern')}")
    else:
        console.print(f"  {icon} [dim]{tool_name}[/dim]")


def _display_tool_result(tool_name: str, result: str) -> None:
    if tool_name == "run_command":
        # Show command output
        lines = result.strip().splitlines()
        shown = lines[:20]
        if len(lines) > 20:
            shown.append(f"... ({len(lines) - 20} more lines)")
        for line in shown:
            console.print(f"    [dim]{line}[/dim]")
    elif tool_name in ("write_file",):
        console.print(f"    [green]{result}[/green]")
    elif result.startswith("Error"):
        console.print(f"    [red]{result[:200]}[/red]")


def _display_summary(
    executor: ToolExecutor,
    commands_run: list[str],
    turns: int,
    total_tokens: int,
) -> None:
    written = list(set(executor.files_written))
    read = list(set(executor.files_read))

    lines = [f"[bold green]✅ Task complete[/bold green] ({turns} turns, {total_tokens:,} tokens)"]

    if written:
        lines.append(f"\n[bold]Files modified ({len(written)}):[/bold]")
        for f in sorted(written):
            action = "modified" if f in executor.files_read else "created"
            lines.append(f"  • {f} [dim]({action})[/dim]")

    if commands_run:
        lines.append(f"\n[bold]Commands run ({len(commands_run)}):[/bold]")
        for cmd in commands_run[:5]:
            lines.append(f"  $ {cmd}")

    console.print(Panel("\n".join(lines), border_style="green"))
