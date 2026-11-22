"""Command-line interface for local workshop task and context management."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .context_manager import ContextError, ContextManager
from .handoff import render_handoff
from .models import TASK_STATUSES, Task
from .providers.policy import FreeTierGate, PolicyDenied, ProviderCatalogError, ProviderRegistry
from .task_store import TaskStore, TaskStoreError


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="workshop",
        description="Lightweight task and handoff manager for the AI Workshop.",
    )
    parser.add_argument("--home", default=".workshop", help="local task data directory (default: .workshop)")
    parser.add_argument("--version", action="version", version=f"workshop {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)

    task = commands.add_parser("task", help="create and manage tasks")
    task_commands = task.add_subparsers(dest="task_command", required=True)
    create = task_commands.add_parser("create", help="create a task")
    create.add_argument("title")
    create.add_argument("--description", default="")
    create.add_argument("--project", default=".")
    task_commands.add_parser("list", help="list saved tasks")
    show = task_commands.add_parser("show", help="show a task")
    show.add_argument("task_id")
    status = task_commands.add_parser("status", help="change a task status")
    status.add_argument("task_id")
    status.add_argument("status", choices=sorted(TASK_STATUSES))
    note = task_commands.add_parser("note", help="append a note to a task")
    note.add_argument("task_id")
    note.add_argument("text")
    handoff = task_commands.add_parser("handoff", help="render a portable assistant handoff")
    handoff.add_argument("task_id")
    handoff.add_argument("--output", type=Path)
    resume = task_commands.add_parser("resume", help="show the saved state and remaining checkpoints")
    resume.add_argument("task_id")

    checkpoint = task_commands.add_parser("checkpoint", help="manage task checkpoints")
    checkpoint_commands = checkpoint.add_subparsers(dest="checkpoint_command", required=True)
    cp_add = checkpoint_commands.add_parser("add", help="add a pending checkpoint")
    cp_add.add_argument("task_id")
    cp_add.add_argument("title")
    cp_list = checkpoint_commands.add_parser("list", help="list checkpoints")
    cp_list.add_argument("task_id")
    cp_done = checkpoint_commands.add_parser("complete", help="mark a checkpoint complete")
    cp_done.add_argument("task_id")
    cp_done.add_argument("checkpoint_id")

    context = commands.add_parser("context", help="build a bounded project-context bundle")
    context_commands = context.add_subparsers(dest="context_command", required=True)
    build = context_commands.add_parser("build", help="load the known context files in priority order")
    build.add_argument("--project", default=".")
    build.add_argument("--max-words", type=int, default=2500)
    build.add_argument("--output", type=Path)

    provider = commands.add_parser("provider", help="inspect provider policies and run a zero-cost preflight")
    provider_commands = provider.add_subparsers(dest="provider_command", required=True)
    provider_list = provider_commands.add_parser("list", help="list locally verified model policies")
    provider_list.add_argument("--catalog", type=Path, default=Path("config/provider-catalog.json"))
    preflight = provider_commands.add_parser("preflight", help="check a model request without making a network call")
    preflight.add_argument("provider")
    preflight.add_argument("model")
    preflight.add_argument("--input-tokens", type=int, required=True)
    preflight.add_argument("--output-tokens", type=int, required=True)
    preflight.add_argument("--region", required=True)
    preflight.add_argument("--catalog", type=Path, default=Path("config/provider-catalog.json"))

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
    if task.checkpoints:
        print("Checkpoints:")
        for item in task.checkpoints:
            marker = "x" if item.status == "done" else " "
            print(f"  [{marker}] {item.id} {item.title}")


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
        for item in tasks:
            print(f"{item.id:<10} {item.status:<12} {item.title}")
        return 0
    if args.task_command == "show":
        _print_task(store.get(args.task_id))
        return 0
    if args.task_command == "status":
        item = store.set_status(args.task_id, args.status)
        print(f"Updated {item.id}: {item.status}")
        return 0
    if args.task_command == "note":
        item = store.add_note(args.task_id, args.text)
        print(f"Added note to {item.id}")
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
    if args.task_command == "resume":
        item = store.get(args.task_id)
        _print_task(item)
        pending = [checkpoint for checkpoint in item.checkpoints if checkpoint.status != "done"]
        print(f"Resume summary: {len(pending)} pending / {len(item.checkpoints)} total checkpoints")
        if pending:
            print("Next suggested step:", pending[0].title)
        else:
            print("No pending checkpoints. Review the task status and notes before continuing.")
        return 0
    if args.task_command == "checkpoint":
        if args.checkpoint_command == "add":
            item = store.add_checkpoint(args.task_id, args.title)
            checkpoint = item.checkpoints[-1]
            print(f"Added checkpoint {checkpoint.id}: {checkpoint.title}")
            return 0
        if args.checkpoint_command == "list":
            item = store.get(args.task_id)
            if not item.checkpoints:
                print("No checkpoints found.")
                return 0
            for checkpoint in item.checkpoints:
                marker = "x" if checkpoint.status == "done" else " "
                print(f"[{marker}] {checkpoint.id} {checkpoint.title}")
            return 0
        if args.checkpoint_command == "complete":
            item = store.complete_checkpoint(args.task_id, args.checkpoint_id)
            print(f"Completed checkpoint {args.checkpoint_id} for task {item.id}")
            return 0
    return 2


def _run_context(args: argparse.Namespace) -> int:
    bundle = ContextManager(args.project, args.max_words).build()
    markdown = bundle.render()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(markdown, encoding="utf-8")
        print(f"Wrote context bundle: {args.output} ({bundle.total_words}/{bundle.max_words} words)")
    else:
        sys.stdout.write(markdown)
        print(
            f"Loaded {len(bundle.files)} context files ({bundle.total_words}/{bundle.max_words} words).",
            file=sys.stderr,
        )
    return 0


def _run_provider(args: argparse.Namespace) -> int:
    registry = ProviderRegistry.load(args.catalog)
    if args.provider_command == "list":
        policies = registry.list_models()
        if not policies:
            print("No model policies are configured. Requests will be denied by default.")
            print("Verify official provider terms before adding entries to config/provider-catalog.json.")
            return 0
        for policy in policies:
            state = "enabled" if policy.enabled else "disabled"
            print(f"{policy.provider}/{policy.model}: {policy.access_type}, {policy.verification_status}, {state}")
        return 0
    try:
        approval = FreeTierGate(registry).authorize(
            provider=args.provider,
            model=args.model,
            input_tokens=args.input_tokens,
            output_tokens=args.output_tokens,
            region=args.region,
        )
    except PolicyDenied as exc:
        print(f"DENIED: {exc}", file=sys.stderr)
        return 2
    print(f"APPROVED: {approval.provider}/{approval.model}")
    print(f"Region: {approval.region}")
    print(f"Estimated input/output tokens: {approval.input_tokens}/{approval.output_tokens}")
    print("Verified model costs: $0.00; no network request was made.")
    return 0


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
    print("OK: no API request was made; no provider credentials are required for local commands.")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "doctor":
            return _doctor(args.home)
        if args.command == "context":
            return _run_context(args)
        if args.command == "provider":
            return _run_provider(args)
        return _run_task(args, TaskStore(args.home))
    except (TaskStoreError, ContextError, ProviderCatalogError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
