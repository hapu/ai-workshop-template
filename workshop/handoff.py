"""Render portable Markdown handoffs for browser and API assistants."""

from .models import Task


def render_handoff(task: Task) -> str:
    """Render task state and checkpoints without including environment secrets."""
    lines = [
        f"# Task handoff: {task.title}",
        "",
        f"- **Task ID:** {task.id}",
        f"- **Status:** {task.status}",
        f"- **Created:** {task.created_at}",
        f"- **Updated:** {task.updated_at}",
        f"- **Project path:** {task.project_path}",
        "",
        "## Objective",
        task.description or "No description supplied.",
        "",
        "## Checkpoints",
    ]
    if task.checkpoints:
        lines.extend(
            f"- [{'x' if item.status == 'done' else ' '}] {item.id} {item.title}"
            for item in task.checkpoints
        )
    else:
        lines.append("- No checkpoints recorded yet.")
    lines.extend(["", "## Notes"])
    if task.notes:
        lines.extend(f"- {note}" for note in task.notes)
    else:
        lines.append("- No notes recorded yet.")
    lines.extend(
        [
            "",
            "## Instructions for the next assistant",
            "1. Inspect the current repository state before editing.",
            "2. Read the project's AGENTS.md, context, TODO, and architecture files when present.",
            "3. Continue the first pending checkpoint; do not repeat completed work without a reason.",
            "4. Make one reviewable change at a time and run the project's checks.",
            "5. Do not expose credentials or use paid services without explicit approval.",
            "6. Summarize changed files, checks, and remaining work.",
            "",
        ]
    )
    return "\n".join(lines)
