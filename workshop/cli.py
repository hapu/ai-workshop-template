"""Command-line interface for local workshop task and context management."""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path

from . import __version__
from .context_manager import ContextError, ContextManager
from .handoff import render_handoff
from .models import TASK_STATUSES, Task
from .providers.policy import FreeTierGate, PolicyDenied, ProviderCatalogError, ProviderRegistry
from .providers.reconciliation import (
    groq_response_headers_to_snapshot,
    openrouter_key_response_to_snapshot,
)
from .providers.usage_ledger import QuotaExceeded, UsageLedger, UsageLedgerError
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
    export_task = task_commands.add_parser("export", help="export a checksummed task bundle")
    export_task.add_argument("task_id")
    export_task.add_argument("--output", type=Path, required=True)
    import_task = task_commands.add_parser("import", help="import a task bundle without overwriting")
    import_task.add_argument("bundle", type=Path)
    recover_task = task_commands.add_parser("recover", help="remove abandoned temporary task files")
    recover_task.add_argument("--older-than-seconds", type=int, default=86400)

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
    preflight.add_argument("--neurons", type=int, default=0, help="conservative estimate for Neuron-metered services")
    preflight.add_argument("--account-scope", default="default", help="legacy local account alias")
    preflight.add_argument("--quota-scope", action="append", default=[], metavar="TYPE=ALIAS", help="quota boundary alias; repeat for organization/project")
    preflight.add_argument("--catalog", type=Path, default=Path("config/provider-catalog.json"))
    preflight.add_argument("--ledger", type=Path, default=Path(".workshop/provider-usage.sqlite3"))

    usage = provider_commands.add_parser("usage", help="show local reserved quota usage")
    usage.add_argument("provider")
    usage.add_argument("model")
    usage.add_argument("--account-scope", default="default")
    usage.add_argument("--quota-scope", action="append", default=[], metavar="TYPE=ALIAS", help="quota boundary alias; repeat for organization/project")
    usage.add_argument("--catalog", type=Path, default=Path("config/provider-catalog.json"))
    usage.add_argument("--ledger", type=Path, default=Path(".workshop/provider-usage.sqlite3"))

    reconcile = provider_commands.add_parser("reconcile", help="import a provider dashboard/API quota snapshot")
    reconcile.add_argument("snapshot_file", type=Path)
    reconcile.add_argument("--catalog", type=Path, default=Path("config/provider-catalog.json"))
    reconcile.add_argument("--ledger", type=Path, default=Path(".workshop/provider-usage.sqlite3"))

    openrouter = provider_commands.add_parser(
        "reconcile-openrouter-key",
        help="convert a saved OpenRouter GET /api/v1/key response into a quota snapshot",
    )
    openrouter.add_argument("response_file", type=Path)
    openrouter.add_argument("--model", required=True)
    openrouter.add_argument("--account-scope", required=True)
    openrouter.add_argument("--captured-at", required=True, help="UTC ISO-8601 time when the response was captured")
    openrouter.add_argument("--snapshot-id", default=None)
    openrouter.add_argument("--catalog", type=Path, default=Path("config/provider-catalog.json"))
    openrouter.add_argument("--ledger", type=Path, default=Path(".workshop/provider-usage.sqlite3"))

    groq = provider_commands.add_parser(
        "reconcile-groq-headers",
        help="convert saved Groq response rate-limit headers into quota snapshots",
    )
    groq.add_argument("headers_file", type=Path)
    groq.add_argument("--model", required=True)
    groq.add_argument("--account-scope", required=True, help="non-secret alias for the Groq organization quota")
    groq.add_argument("--captured-at", required=True, help="UTC ISO-8601 time when the response headers were received")
    groq.add_argument("--snapshot-id", default=None)
    groq.add_argument("--catalog", type=Path, default=Path("config/provider-catalog.json"))
    groq.add_argument("--ledger", type=Path, default=Path(".workshop/provider-usage.sqlite3"))

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
    if args.task_command == "export":
        output = store.export_bundle(args.task_id, args.output)
        print(f"Exported task {args.task_id}: {output}")
        return 0
    if args.task_command == "import":
        item = store.import_bundle(args.bundle)
        print(f"Imported task {item.id}: {item.title}")
        return 0
    if args.task_command == "recover":
        removed = store.recover(older_than_seconds=args.older_than_seconds)
        print(f"Removed {removed} abandoned temporary file(s).")
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


def _parse_quota_scopes(values: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in values:
        if "=" not in item:
            raise UsageLedgerError("Each --quota-scope must use TYPE=ALIAS")
        scope, alias = item.split("=", 1)
        if scope not in {"organization", "project"} or not alias.strip():
            raise UsageLedgerError("Quota scopes must use organization or project with a non-empty alias")
        if scope in result:
            raise UsageLedgerError(f"Quota scope {scope} was supplied more than once")
        result[scope] = alias.strip()
    return result


def _run_provider(args: argparse.Namespace) -> int:
    registry = ProviderRegistry.load(args.catalog)
    if args.provider_command == "reconcile":
        try:
            raw = json.loads(args.snapshot_file.read_text(encoding="utf-8"))
            if not isinstance(raw, dict) or not isinstance(raw.get("provider"), str) or not isinstance(raw.get("model"), str):
                raise ValueError("Snapshot file must contain string provider and model fields")
            policy = registry.require(raw["provider"], raw["model"])
            snapshot = UsageLedger(args.ledger).import_snapshot(raw, policy)
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError, UsageLedgerError, PolicyDenied) as exc:
            print(f"RECONCILIATION REJECTED: {exc}", file=sys.stderr)
            return 2
        print(f"Imported quota snapshot: {snapshot.snapshot_id}")
        print(f"Provider/model: {snapshot.provider}/{snapshot.model}")
        print(f"Account scope: {snapshot.account_scope}")
        print(f"Captured at: {snapshot.captured_at_text()}")
        print(f"Quota entries imported: {len(snapshot.quotas)}")
        print("No API request was made.")
        return 0

    if args.provider_command == "reconcile-openrouter-key":
        try:
            payload = json.loads(args.response_file.read_text(encoding="utf-8"))
            policy = registry.require("openrouter", args.model)
            canonical = openrouter_key_response_to_snapshot(
                payload, policy, account_scope=args.account_scope,
                captured_at=args.captured_at, snapshot_id=args.snapshot_id or uuid.uuid4().hex,
            )
            snapshot = UsageLedger(args.ledger).import_snapshot(canonical, policy)
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError, UsageLedgerError, PolicyDenied) as exc:
            print(f"RECONCILIATION REJECTED: {exc}", file=sys.stderr)
            return 2
        print(f"Imported OpenRouter quota snapshot: {snapshot.snapshot_id}")
        print(f"Model: {snapshot.model}; account scope: {snapshot.account_scope}")
        print(f"Captured at: {snapshot.captured_at_text()}")
        print("Only the OpenRouter free-model daily request counter was imported.")
        print("No API request was made by this command.")
        return 0

    if args.provider_command == "reconcile-groq-headers":
        try:
            headers = json.loads(args.headers_file.read_text(encoding="utf-8"))
            policy = registry.require("groq", args.model)
            canonical = groq_response_headers_to_snapshot(
                headers, policy, account_scope=args.account_scope,
                captured_at=args.captured_at, snapshot_id=args.snapshot_id or uuid.uuid4().hex,
            )
            snapshot = UsageLedger(args.ledger).import_snapshot(canonical, policy)
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError, UsageLedgerError, PolicyDenied) as exc:
            print(f"RECONCILIATION REJECTED: {exc}", file=sys.stderr)
            return 2
        print(f"Imported Groq response-header snapshot: {snapshot.snapshot_id}")
        print(f"Model: {snapshot.model}; account scope: {snapshot.account_scope}")
        print(f"Captured at: {snapshot.captured_at_text()}")
        print("Imported quota dimensions: " + ", ".join(
            f"{item.metric}/{item.window_seconds}s" for item in snapshot.quotas
        ))
        print("No API request was made by this command.")
        return 0

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
        policy = registry.require(args.provider, args.model)
    except PolicyDenied as exc:
        print(f"DENIED: {exc}", file=sys.stderr)
        return 2
    ledger = UsageLedger(args.ledger)
    quota_scopes = _parse_quota_scopes(args.quota_scope)
    if args.provider_command == "usage":
        statuses = ledger.usage(policy, account_scope=args.account_scope, quota_scopes=quota_scopes)
        print(f"Local usage for {policy.provider}/{policy.model} (account scope: {args.account_scope})")
        for item in statuses:
            if not item.reconciled:
                print(
                    f"{item.metric} / {item.window_seconds}s / {item.scope}={item.scope_id}: "
                    f"NOT RECONCILED; local-only reservations={item.local_used}"
                )
                continue
            print(
                f"{item.metric} / {item.window_seconds}s / {item.scope}={item.scope_id}: "
                f"{item.used}/{item.limit} used "
                f"(external snapshot={item.snapshot_used}, later local={item.local_used}); "
                f"{item.remaining} remaining"
            )
            print(
                f"  Snapshot: {item.snapshot_captured_at}; resets: {item.snapshot_reset_at}; "
                f"age: {item.snapshot_age_seconds}s; source: {item.snapshot_source_url}"
            )
        print("Only a fresh imported snapshot plus reservations in this local ledger are represented.")
        return 0

    try:
        approval = FreeTierGate(registry).authorize(
            provider=args.provider,
            model=args.model,
            input_tokens=args.input_tokens,
            output_tokens=args.output_tokens,
            region=args.region,
        )
        statuses = ledger.preflight(
            policy,
            account_scope=args.account_scope,
            quota_scopes=quota_scopes,
            input_tokens=approval.input_tokens,
            output_tokens=approval.output_tokens,
            neurons=args.neurons,
        )
    except (PolicyDenied, QuotaExceeded, UsageLedgerError) as exc:
        print(f"DENIED: {exc}", file=sys.stderr)
        return 2
    print(f"APPROVED: {approval.provider}/{approval.model}")
    print(f"Region: {approval.region}")
    print(f"Estimated input/output tokens: {approval.input_tokens}/{approval.output_tokens}")
    print("Verified model costs: $0.00; no network request was made.")
    for item in statuses:
        print(
            f"Quota {item.metric}/{item.window_seconds}s: "
            f"{item.used}+{item.requested}/{item.limit}; "
            f"{item.remaining_after_request} remaining after this request"
        )
    print("Preflight does not reserve usage. A provider adapter must call UsageLedger.reserve immediately before network I/O.")
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
    except (TaskStoreError, ContextError, ProviderCatalogError, UsageLedgerError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
