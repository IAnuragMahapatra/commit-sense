"""Rule engine — deterministic checks run before LLM. Returns a list of Flag objects."""

import re
from dataclasses import dataclass
from pathlib import Path

from diff.parser import FileDiff
from llm.config import load_config

GENERIC_SUBJECTS = {
    "fix",
    "wip",
    "update",
    "changes",
    "minor",
    "temp",
    "more",
    "stuff",
    "misc",
    "done",
    "test",
    "work",
}

CONVENTIONAL_RE = re.compile(
    r"^(feat|fix|docs|style|refactor|perf|test|chore|ci|build|revert)"
    r"(\(.+\))?(!)?: .+",
    re.IGNORECASE,
)

BREAKING_KEYWORDS = ("breaking", "removed", "deleted", "dropped")

# Patterns to detect function definition changes in diff lines
_PY_DEF_RE = re.compile(r"^[+-]\s*def\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(")
_JS_DEF_RE = re.compile(
    r"^[+-]\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*[\(\{]"
)
_JS_ARROW_RE = re.compile(
    r"^[+-]\s*(?:export\s+)?(?:const|let|var)\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*(?:async\s*)?\("
)


@dataclass
class Flag:
    rule: str
    severity: str  # "info" | "warning" | "critical"
    detail: str


def run_rules(
    message: str,
    file_diffs: list[FileDiff],
    ast_results: dict[str, dict],
) -> list[Flag]:
    """
    Run all deterministic rules against a commit.

    Args:
        message:     The commit message.
        file_diffs:  Output of diff.parser.get_diff().
        ast_results: Output of diff.ast_extractor.extract_definitions() per file path.

    Returns:
        List of Flag objects — one per triggered rule.
    """
    cfg = load_config().get("rules", {})
    flags: list[Flag] = []
    msg = message.strip()
    msg_lower = msg.lower()

    # 1. Diff > max_diff_lines
    max_lines = int(cfg.get("max_diff_lines", 500))
    total_loc = sum(f.additions + f.deletions for f in file_diffs)
    if total_loc > max_lines:
        flags.append(
            Flag(
                "large_diff",
                "warning",
                f"Diff is {total_loc} LOC (limit: {max_lines})",
            )
        )

    # 2. Message under min_message_length
    min_len = int(cfg.get("min_message_length", 20))
    if len(msg) < min_len:
        flags.append(
            Flag(
                "short_message",
                "warning",
                f"Message is {len(msg)} chars (min: {min_len})",
            )
        )

    # 3. Generic message — check the subject (after conventional prefix if present)
    if cfg.get("block_generics", True):
        subject = re.sub(
            r"^[a-z]+(\(.+\))?(!)?: ", "", msg, flags=re.IGNORECASE
        ).strip()
        first_word = subject.lower().split()[0].rstrip(":!,.") if subject else ""
        if first_word in GENERIC_SUBJECTS or subject.lower() in GENERIC_SUBJECTS:
            flags.append(
                Flag(
                    "generic_message",
                    "critical",
                    f"Generic commit subject: '{subject}'",
                )
            )

    # 4. Conventional commits format
    if cfg.get("require_conventional_commits", True):
        if not CONVENTIONAL_RE.match(msg):
            flags.append(
                Flag(
                    "conventional_commits",
                    "warning",
                    "Message doesn't follow conventional commits format: type(scope): subject",
                )
            )

    # 5. Message doesn't mention any changed module
    # Collect both filenames and directory names as potential module references
    changed_modules = set()
    for f in file_diffs:
        p = Path(f.path)
        # Add filename stem (excluding generic names)
        if p.stem not in ("__init__", "index", ""):
            changed_modules.add(p.stem.lower())
        # Add parent directory names (excluding root and generic names)
        for part in p.parts[:-1]:  # exclude the filename itself
            if part not in (".", "..", "src", "lib", "utils"):
                changed_modules.add(part.lower())

    # Check if any module is mentioned in the message
    if changed_modules and not any(mod in msg_lower for mod in changed_modules):
        flags.append(
            Flag(
                "missing_module_ref",
                "warning",
                f"Message doesn't reference any changed module: {', '.join(sorted(changed_modules))}",
            )
        )

    # 6. Public function signature changed, not mentioned in message
    # Only fires if a function *definition line* was actually modified in the diff.
    changed_fns: list[str] = []
    for fd in file_diffs:
        ext = Path(fd.path).suffix.lower()
        all_hunk_lines = [line for hunk in fd.hunks for line in hunk.lines]
        if ext == ".py":
            for line in all_hunk_lines:
                m = _PY_DEF_RE.match(line)
                if m:
                    name = m.group(1)
                    if not name.startswith("_"):  # public only
                        changed_fns.append(name)
        elif ext in (".js", ".mjs", ".cjs", ".ts", ".tsx"):
            for line in all_hunk_lines:
                m = _JS_DEF_RE.match(line) or _JS_ARROW_RE.match(line)
                if m:
                    changed_fns.append(m.group(1))

    unmentioned = [fn for fn in changed_fns if fn and fn.lower() not in msg_lower]
    if changed_fns and unmentioned:
        flags.append(
            Flag(
                "signature_not_in_message",
                "warning",
                f"Function definitions changed but not in message: {', '.join(unmentioned[:5])}",
            )
        )

    # 7. Multiple unrelated modules in one commit
    top_dirs = {
        Path(f.path).parts[0] for f in file_diffs if len(Path(f.path).parts) > 1
    }
    if len(top_dirs) > 2:
        flags.append(
            Flag(
                "multiple_modules",
                "info",
                f"Changes span {len(top_dirs)} top-level modules: {', '.join(sorted(top_dirs))}",
            )
        )

    # 8. Inconsistent naming across changed files
    stems = [Path(f.path).stem for f in file_diffs]
    has_snake = any("_" in s for s in stems)
    has_camel = any(re.search(r"[a-z][A-Z]", s) for s in stems)
    if has_snake and has_camel:
        flags.append(
            Flag(
                "inconsistent_naming",
                "info",
                "Changed files mix snake_case and camelCase naming conventions",
            )
        )

    # 9. Breaking change without `!` or `BREAKING CHANGE`
    removed_lines = " ".join(
        line
        for fd in file_diffs
        for hunk in fd.hunks
        for line in hunk.lines
        if line.startswith("-")
    ).lower()
    looks_breaking = any(kw in removed_lines for kw in BREAKING_KEYWORDS)
    prefix = msg.split(":")[0]
    has_marker = "!" in prefix or "BREAKING CHANGE" in msg
    if looks_breaking and not has_marker:
        flags.append(
            Flag(
                "breaking_no_marker",
                "critical",
                "Possible breaking change detected without '!' or 'BREAKING CHANGE' in message",
            )
        )

    return flags
