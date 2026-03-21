"""Pre-push hook — lightweight: diff → rules → rewrite → amend → POST."""

import os
import subprocess
import sys

# Force UTF-8 encoding on Windows
if sys.platform == "win32":
    import io

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    else:
        sys.stdout = io.TextIOWrapper(
            sys.stdout.buffer, encoding="utf-8", errors="replace"
        )
        sys.stderr = io.TextIOWrapper(
            sys.stderr.buffer, encoding="utf-8", errors="replace"
        )

import requests

from diff.parser import get_diff
from llm.config import load_config
from rewriter.rewriter import rewrite_message
from rules.engine import run_rules
from rules.scorer import compute_score


def _get_unpushed_commits(remote_ref: str) -> list[str]:
    """Get list of commit SHAs that haven't been pushed yet."""
    try:
        # Get commits that are in HEAD but not in the remote ref
        output = subprocess.check_output(
            ["git", "rev-list", f"{remote_ref}..HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        if not output:
            return []
        return output.split("\n")
    except subprocess.CalledProcessError:
        # Remote ref doesn't exist (first push) - get all commits
        try:
            output = subprocess.check_output(
                ["git", "rev-list", "HEAD"],
                text=True,
            ).strip()
            return output.split("\n") if output else []
        except subprocess.CalledProcessError:
            return []


def _get_commit_info(sha: str) -> tuple[str, str]:
    """Return (sha, commit_message) for the given commit."""
    message = subprocess.check_output(
        ["git", "log", "-1", "--pretty=%B", sha], text=True
    ).strip()
    return sha, message


def _get_repo_name() -> str:
    """Return the remote URL or local directory name."""
    try:
        return subprocess.check_output(
            ["git", "remote", "get-url", "origin"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except subprocess.CalledProcessError:
        return os.path.basename(os.getcwd())


def _build_diff_summary(file_diffs) -> str:
    """Produce a concise diff summary for the rewriter prompt."""
    lines = []
    for fd in file_diffs:
        lines.append(f"File: {fd.path} (+{fd.additions}/-{fd.deletions})")
        for hunk in fd.hunks[:2]:
            for line in hunk.lines[:10]:
                lines.append(f"  {line}")
    return "\n".join(lines[:60])


def _post_to_dashboard(payload: dict) -> None:
    """POST a lightweight hook record to the dashboard. Never raises."""
    cfg = load_config()
    dashboard = cfg.get("dashboard", {})
    url = dashboard.get("url", "").rstrip("/")
    token = dashboard.get("token", "")

    if not url:
        return

    try:
        resp = requests.post(
            f"{url}/api/reports",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        resp.raise_for_status()
        print(f"  → Dashboard notified (status {resp.status_code})")
    except Exception as exc:
        print(f"  → Dashboard POST failed (non-blocking): {exc}", file=sys.stderr)


def _process_commit(sha: str, is_head: bool) -> bool:
    """
    Process a single commit. Returns True if commit has issues that need fixing.
    """
    _, message = _get_commit_info(sha)
    print(f"\n[CommitSense] {sha[:8]}")
    print(f"   Message: {message[:72]}")

    # 1. Git diff (no AST)
    try:
        file_diffs = get_diff(commit_ref=sha)
    except RuntimeError as exc:
        print(f"  ⚠ Diff failed: {exc} — skipping")
        return False

    if not file_diffs:
        print("  ✓ No file changes detected")
        return False

    # 2. Rule engine (empty ast_results — no AST in hook)
    flags = run_rules(message, file_diffs, ast_results={})
    score_data = compute_score(flags)

    if not flags:
        print(f"  ✓ Message looks good (grade {score_data['grade']})")
        return False

    # 3. Show flags
    print(f"\n  ⚠ Grade {score_data['grade']} — {len(flags)} issue(s):")
    for f in flags:
        icon = {"critical": "[!]", "warning": "[W]", "info": "[i]"}.get(f.severity, "•")
        print(f"    {icon} [{f.severity}] {f.detail}")

    # 4. Rewrite via LLM
    diff_summary = _build_diff_summary(file_diffs)
    print("\n  ⏳ Asking LLM for a rewrite...")

    try:
        result = rewrite_message(message, flags, diff_summary)
    except RuntimeError as exc:
        print(f"  ⚠ Rewrite failed: {exc} — keeping original")
        return True  # Has issues but can't fix

    print("\n  📝 Suggested rewrite:")
    print(f"     Original:  {message}")
    print(f"     Rewritten: {result.rewritten}")
    print(f"     Reason:    {result.explanation}")

    # 5. Amend or skip
    cfg = load_config()
    auto_amend = cfg.get("rewrite", {}).get("auto_amend", False)

    if auto_amend:
        accept = True
        print("\n  ⚡ auto_amend is on — amending automatically")
    else:
        # Don't prompt during pre-push - just report the issue
        print("\n  ⚠ Commit needs fixing (set auto_amend: true to fix automatically)")
        return True  # Has issues

    if not accept:
        return True  # Has issues

    # 6. Amend the commit (only if it's HEAD and auto_amend is true)
    if not is_head:
        print("  ⚠ Cannot amend non-HEAD commit — use interactive rebase manually")
        return True  # Has issues

    try:
        subprocess.run(
            ["git", "commit", "--amend", "-m", result.rewritten],
            check=True,
            capture_output=True,
            text=True,
        )
        new_sha = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True
        ).strip()
        print(f"  ✓ Commit amended — new SHA: {new_sha[:8]}")
    except subprocess.CalledProcessError as exc:
        print(f"  ⚠ Amend failed: {exc.stderr.strip()} — keeping original")
        return True  # Has issues

    # 7. POST lightweight record to dashboard
    _post_to_dashboard(
        {
            "sha": new_sha,
            "repo": _get_repo_name(),
            "original_message": message,
            "rewritten_message": result.rewritten,
            "amended": True,
        }
    )

    print("  ✓ Done")
    return False  # Fixed


def main() -> None:
    """Run the pre-push hook pipeline. Exits with 1 to block push if commits need fixing."""
    # Read stdin to get the refs being pushed
    # Format: <local ref> <local sha> <remote ref> <remote sha>
    stdin_input = sys.stdin.read().strip()

    # If no stdin (manual execution), check against origin/main
    if not stdin_input:
        print("\n[CommitSense] Manual execution - checking against origin/main")
        try:
            remote_ref = "origin/main"
            unpushed = _get_unpushed_commits(remote_ref)
        except Exception:
            print("[CommitSense] Could not determine unpushed commits")
            return
    else:
        # Parse stdin from git push
        lines = stdin_input.split("\n")
        found = False
        for line in lines:
            parts = line.split()
            if len(parts) < 4:
                continue

            local_ref, local_sha, remote_ref, remote_sha = parts[:4]
            unpushed = _get_unpushed_commits(remote_ref)
            found = True
            break

        if not found:
            print("\n[CommitSense] No refs to push")
            return

    if not unpushed:
        print("\n[CommitSense] All commits already pushed")
        return

    print(f"\n[CommitSense] Checking {len(unpushed)} unpushed commit(s)...")

    # Process commits from oldest to newest (reverse order)
    unpushed.reverse()

    needs_fixing = []
    for i, sha in enumerate(unpushed):
        is_head = i == len(unpushed) - 1  # Last commit is HEAD
        has_issues = _process_commit(sha, is_head)

        if has_issues:
            needs_fixing.append((sha, is_head))

    if not needs_fixing:
        print("\n[CommitSense] ✓ All commits look good")
        return

    # Check if only HEAD needs fixing
    only_head_needs_fix = len(needs_fixing) == 1 and needs_fixing[0][1]

    if not only_head_needs_fix:
        print(
            f"\n[CommitSense] ⚠ Push blocked - {len(needs_fixing)} commit(s) have issues"
        )
        print("Older commits need fixing - use interactive rebase:")
        print(f"  git rebase -i HEAD~{len(unpushed)}")
        sys.exit(1)

        # Only HEAD needs fixing - check if auto_amend is enabled
        cfg = load_config()
        auto_amend = cfg.get("rewrite", {}).get("auto_amend", False)

        if not auto_amend:
            print("\n[CommitSense] ⚠ Push blocked - HEAD commit has issues")
            print("Set auto_amend: true in commitsense.yml to fix automatically")
            print("Or fix manually and commit again")
            sys.exit(1)

        print("\n[CommitSense] ✓ HEAD was auto-fixed, push allowed")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"  ⚠ CommitSense hook error: {exc}", file=sys.stderr)
        sys.exit(1)  # Block push on error
