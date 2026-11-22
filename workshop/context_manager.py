"""Load a safe, bounded bundle of project context files."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


CONTEXT_FILES: tuple[tuple[str, int], ...] = (
    ("AGENTS.md", 500),
    ("PROJECT_CONTEXT.md", 800),
    ("HANDOFF.md", 300),
    ("TODO.md", 500),
    ("docs/ARCHITECTURE.md", 600),
    ("docs/WORKFLOW.md", 800),
)


class ContextError(Exception):
    """Raised when project context cannot be read safely or fit its budget."""


@dataclass(frozen=True, slots=True)
class ContextFile:
    path: str
    content: str
    words: int
    limit: int


@dataclass(frozen=True, slots=True)
class ContextBundle:
    root: Path
    files: tuple[ContextFile, ...]
    total_words: int
    max_words: int

    def render(self) -> str:
        sections = [
            "# Project context bundle",
            "",
            f"- Project root: {self.root}",
            f"- Files included: {len(self.files)}",
            f"- Words: {self.total_words} / {self.max_words}",
            "",
        ]
        for item in self.files:
            sections.extend(
                [
                    f"---\n\n## Source: {item.path} ({item.words}/{item.limit} words)\n",
                    item.content.rstrip(),
                    "",
                ]
            )
        return "\n".join(sections).rstrip() + "\n"


class ContextManager:
    """Read only known project context paths and enforce per-file and total budgets."""

    def __init__(self, project_root: Path | str = ".", max_words: int = 2500) -> None:
        if max_words < 1:
            raise ContextError("Context budget must be greater than zero")
        self.root = Path(project_root).expanduser().resolve()
        self.max_words = max_words

    def build(self) -> ContextBundle:
        if not self.root.is_dir():
            raise ContextError(f"Project directory does not exist: {self.root}")
        loaded: list[ContextFile] = []
        total = 0
        for relative, limit in CONTEXT_FILES:
            candidate = self.root / relative
            if not candidate.exists():
                continue
            resolved = candidate.resolve()
            try:
                resolved.relative_to(self.root)
            except ValueError as exc:
                raise ContextError(f"Context path escapes project directory: {relative}") from exc
            if not resolved.is_file():
                raise ContextError(f"Context path is not a regular file: {relative}")
            try:
                content = resolved.read_text(encoding="utf-8")
            except (OSError, UnicodeError) as exc:
                raise ContextError(f"Could not read {relative}: {exc}") from exc
            words = len(content.split())
            if words > limit:
                raise ContextError(
                    f"{relative} exceeds its {limit}-word limit ({words} words). "
                    "Trim the file before generating a context bundle."
                )
            if not content.strip():
                continue
            total += words
            if total > self.max_words:
                raise ContextError(
                    f"Context bundle exceeds its {self.max_words}-word budget "
                    f"({total} words). Reduce source files or raise --max-words."
                )
            loaded.append(ContextFile(relative, content, words, limit))
        if not loaded:
            raise ContextError(
                "No project context files were found. Expected one or more of: "
                + ", ".join(path for path, _ in CONTEXT_FILES)
            )
        return ContextBundle(self.root, tuple(loaded), total, self.max_words)
