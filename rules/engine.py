"""Rule engine — deterministic checks run before LLM. Returns a list of Flag objects."""

import re
from dataclasses import dataclass
from pathlib import Path

from diff.parser import FileDiff
from llm.config import load_config

GENERIC_SUBJECTS = {
    "fix", "wip", "update", "changes", "minor", "temp",
    "more", "stuff", "misc", "done", "test", "work",
}

CONVENTIONAL_RE = re.compile(
    r"^(feat|fix|docs|style|refactor|perf|test|chore|ci|build|revert)"
    r"(\(.+\))?(!)?: .+",
    re.IGNORECASE,
)

BREAKING_KEYWORDS = ("breaking", "removed", "deleted", "dropped")


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
        flags.append(Flag(
            "large_diff", "warning",
            f"Diff is {total_loc} LOC (limit: {max_lines})",
        ))

    # 2. Message under min_message_length
    min_len = int(cfg.get("min_message_length", 20))
    if len(msg) < min_len:
        flags.append(Flag(
            "short_message", "warning",
            f"Message is {len(msg)} chars (min: {min_len})",
        ))

    # 3. Generic message — check the subject (after conventional prefix if present)
    if cfg.get("block_generics", True):
        subject = re.sub(r"^[a-z]+(\(.+\))?(!)?: ", "", msg, flags=re.IGNORECASE).strip()
        first_word = subject.lower().split()[0].rstrip(":!,.") if subject else ""
        if first_word in GENERIC_SUBJECTS or subject.lower() in GENERIC_SUBJECTS:
            flags.append(Flag(
                "generic_message", "critical",
                f"Generic commit subject: '{subject}'",
            ))

    # 4. Conventional commits format
    if cfg.get("require_conventional_commits", True):
        if not CONVENTIONAL_RE.match(msg):
            flags.append(Flag(
                "conventional_commits", "warning",
                "Message doesn't follow conventional commits format: type(scope): subject",
            ))

    # 5. Message doesn't mention any changed module
    # Exclude __init__ and similar non-descriptive stems
    changed_modules = {
        Path(f.path).stem.lower()
        for f in file_diffs
        if Path(f.path).stem not in ("__init__", "index", "")
    }
    if changed_modules and not any(mod in msg_lower for mod in changed_modules):
        flags.append(Flag(
            "missing_module_ref", "warning",
            f"Message doesn't reference any changed module: {', '.join(sorted(changed_modules))}",
        ))

    # 6. Public function signature changed, not mentioned in message
    public_fns: list[str] = []
    for path, defs in ast_results.items():
        ext = Path(path).suffix.lower()
        # Python: public = no leading underscore
        if ext == ".py":
            public_fns.extend(fn for fn in defs.get("functions", []) if not fn.startswith("_"))
        else:
            # JS/TS: exported names are the public surface
            public_fns.extend(defs.get("exports", []))

    unmentioned = [fn for fn in public_fns if fn and fn.lower() not in msg_lower]
    if public_fns and unmentioned:
        flags.append(Flag(
            "signature_not_in_message", "critical",
            f"Public functions changed but not in message: {', '.join(unmentioned[:5])}",
        ))

    # 7. Multiple unrelated modules in one commit
    top_dirs = {
        Path(f.path).parts[0]
        for f in file_diffs
        if len(Path(f.path).parts) > 1
    }
    if len(top_dirs) > 2:
        flags.append(Flag(
            "multiple_modules", "info",
            f"Changes span {len(top_dirs)} top-level modules: {', '.join(sorted(top_dirs))}",
        ))

    # 8. Inconsistent naming across changed files
    stems = [Path(f.path).stem for f in file_diffs]
    has_snake = any("_" in s for s in stems)
    has_camel = any(re.search(r"[a-z][A-Z]", s) for s in stems)
    if has_snake and has_camel:
        flags.append(Flag(
            "inconsistent_naming", "info",
            "Changed files mix snake_case and camelCase naming conventions",
        ))

    # 9. Breaking change without `!` or `BREAKING CHANGE`
    removed_lines = " ".join(
        line for fd in file_diffs
        for hunk in fd.hunks
        for line in hunk.lines
        if line.startswith("-")
    ).lower()
    looks_breaking = any(kw in removed_lines for kw in BREAKING_KEYWORDS)
    prefix = msg.split(":")[0]
    has_marker = "!" in prefix or "BREAKING CHANGE" in msg
    if looks_breaking and not has_marker:
        flags.append(Flag(
            "breaking_no_marker", "critical",
            "Possible breaking change detected without '!' or 'BREAKING CHANGE' in message",
        ))

    return flags
