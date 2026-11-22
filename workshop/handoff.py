"""Render portable Markdown handoffs for browser and API assistants."""

from .models import Task


def render_handoff(task: Task) -> str:
    """Render a concise handoff without including environment secrets."""
    lines = [
        f"# Task handoff: {task.title}",
        "",
        f"- **Task ID:** `{task.id}`",
        f"- **Status:** `{task.status}`",
        f"- **Created:** {task.created_at}",
        f"- **Updated:** {task.updated_at}",
        f"- **Project path:** `{task.project_path}`",
        "",
        "## Objective",
        task.description or "No description supplied.",
        "",
        "## Notes",
    ]
    if task.notes:
        lines.extend(f"- {note}" for note in task.notes)
    else:
        lines.append("- No notes recorded yet.")
    lines.extend(
        [
            "",
            "## Instructions for the next assistant",
            "1. Inspect the current repository state before editing.",
            "2. Read the project's `AGENTS.md`, context, TODO, and architecture files when present.",
            "3. Make one reviewable change at a time and run the project's checks.",
            "4. Do not expose credentials or use paid services without explicit approval.",
            "5. Summarize changed files, checks, and remaining work.",
            "",
        ]
    )
    return "\n".join(lines)
