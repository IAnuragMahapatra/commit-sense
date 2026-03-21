"""Git diff parser — runs git diff and parses output into structured FileDiff objects."""

import subprocess
from dataclasses import dataclass, field


@dataclass
class Hunk:
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    lines: list[str] = field(default_factory=list)


@dataclass
class FileDiff:
    path: str
    additions: int
    deletions: int
    hunks: list[Hunk] = field(default_factory=list)


def get_diff(repo_path: str = ".", commit_ref: str = "HEAD") -> list[FileDiff]:
    """
    Run `git diff` for the given commit and return parsed file diffs.

    Args:
        repo_path: Path to the git repository
        commit_ref: Commit reference (SHA, HEAD, etc.) to analyze

    Returns a list of FileDiff — one per changed file.
    Raises RuntimeError if git diff fails.
    """
    result = subprocess.run(
        ["git", "diff", f"{commit_ref}~1", commit_ref],
        cwd=repo_path,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    if result.returncode != 0:
        raise RuntimeError(f"git diff failed: {result.stderr.strip()}")

    return _parse_diff(result.stdout)


def _parse_diff(raw: str) -> list[FileDiff]:
    files: list[FileDiff] = []
    current_file: FileDiff | None = None
    current_hunk: Hunk | None = None

    # Handle empty or None diff (initial commits, merges, etc.)
    if not raw:
        return files

    for line in raw.splitlines():
        # New file block: diff --git a/path b/path
        if line.startswith("diff --git "):
            if current_hunk and current_file:
                current_file.hunks.append(current_hunk)
                current_hunk = None
            if current_file:
                files.append(current_file)
            # Extract the b/ path (handles spaces in filenames less fragile than split)
            parts = line[len("diff --git ") :].split(" b/", 1)
            path = parts[1] if len(parts) == 2 else line.split()[-1].lstrip("b/")
            current_file = FileDiff(path=path, additions=0, deletions=0)

        # Hunk header: @@ -old_start,old_count +new_start,new_count @@
        elif line.startswith("@@") and current_file:
            if current_hunk:
                current_file.hunks.append(current_hunk)
            header = line.split("@@")[1].strip()
            old_part, new_part = header.split(" ")
            old_start, old_count = _parse_range(old_part.lstrip("-"))
            new_start, new_count = _parse_range(new_part.lstrip("+"))
            current_hunk = Hunk(old_start, old_count, new_start, new_count)

        elif current_hunk is not None and current_file is not None:
            if line.startswith("+") and not line.startswith("+++"):
                current_file.additions += 1
                current_hunk.lines.append(line)
            elif line.startswith("-") and not line.startswith("---"):
                current_file.deletions += 1
                current_hunk.lines.append(line)
            elif line.startswith(" "):
                current_hunk.lines.append(line)

    # Flush last hunk and file
    if current_hunk and current_file:
        current_file.hunks.append(current_hunk)
    if current_file:
        files.append(current_file)

    return files


def _parse_range(s: str) -> tuple[int, int]:
    """Parse '10,5' or '10' into (start, count)."""
    if "," in s:
        start, count = s.split(",", 1)
        return int(start), int(count)
    return int(s), 1
