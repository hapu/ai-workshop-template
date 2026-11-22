"""Command-line interface for local workshop task management."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .handoff import render_handoff
from .models import TASK_STATUSES, Task
from .task_store import TaskStore, TaskStoreError


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="workshop",
        description="Lightweight task and handoff manager for the AI Workshop.",
    )
    parser.add_argument(
        "--home",
        default=".workshop",
        help="directory for local task data (default: .workshop)",
    )
    parser.add_argument("--version", action="version", version=f"workshop {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)

    task = commands.add_parser("task", help="create and manage tasks")
    task_commands = task.add_subparsers(dest="task_command", required=True)

    create = task_commands.add_parser("create", help="create a task")
    create.add_argument("title", help="short task title")
    create.add_argument("--description", default="", help="task objective and acceptance criteria")
    create.add_argument("--project", default=".", help="project directory (default: current directory)")

    task_commands.add_parser("list", help="list saved tasks")

    show = task_commands.add_parser("show", help="show a task")
    show.add_argument("task_id")

    status = task_commands.add_parser("status", help="change a task status")
    status.add_argument("task_id")
    status.add_argument("status", choices=sorted(TASK_STATUSES))

    note = task_commands.add_parser("note", help="append a note to a task")
    note.add_argument("task_id")
    note.add_argument("text", help="note text")

    handoff = task_commands.add_parser("handoff", help="render a portable assistant handoff")
    handoff.add_argument("task_id")
    handoff.add_argument("--output", type=Path, help="write Markdown to this file instead of stdout")

    commands.add_parser("doctor", help="check the local Python and workspace environment")
    return parser


def _print_task(task: Task) -> None:
    print(f"ID:          {task.id}")
    print(f"Title:       {task.title}")
    print(f"Status:      {task.status}")
    print(f"Project:     {task.project_path}")
    print(f"Created:     {task.created_at}")
    print(f"Updated:     {task.updated_at}")
    if task.description:
        print(f"Description: {task.description}")
    for note in task.notes:
        print(f"Note:        {note}")


def _run_task(args: argparse.Namespace, store: TaskStore) -> int:
    if args.task_command == "create":
        task = store.create(args.title, args.description, args.project)
        print(f"Created task {task.id}: {task.title}")
        print(f"Next: python3 -m workshop --home {args.home} task handoff {task.id}")
        return 0
    if args.task_command == "list":
        tasks = store.list()
        if not tasks:
            print("No tasks found.")
            return 0
        print(f"{'ID':<10} {'STATUS':<12} TITLE")
        for task in tasks:
            print(f"{task.id:<10} {task.status:<12} {task.title}")
        return 0
    if args.task_command == "show":
        _print_task(store.get(args.task_id))
        return 0
    if args.task_command == "status":
        task = store.set_status(args.task_id, args.status)
        print(f"Updated {task.id}: {task.status}")
        return 0
    if args.task_command == "note":
        task = store.add_note(args.task_id, args.text)
        print(f"Added note to {task.id}")
        return 0
    if args.task_command == "handoff":
        markdown = render_handoff(store.get(args.task_id))
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(markdown, encoding="utf-8")
            print(f"Wrote handoff: {args.output}")
        else:
            sys.stdout.write(markdown)
        return 0
    return 2


def _doctor(home: str) -> int:
    version = sys.version_info
    print(f"Python: {version.major}.{version.minor}.{version.micro}")
    if version < (3, 10):
        print("FAIL: Python 3.10 or newer is required.")
        return 1
    print("OK: Python version supported.")
    directory = Path(home).expanduser().resolve()
    try:
        directory.mkdir(parents=True, exist_ok=True)
        probe = directory / ".write-test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError as exc:
        print(f"FAIL: workspace is not writable: {exc}")
        return 1
    print(f"OK: workspace is writable: {directory}")
    print("OK: no API request was made; no provider credentials are required for local task commands.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "doctor":
            return _doctor(args.home)
        return _run_task(args, TaskStore(args.home))
    except TaskStoreError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
