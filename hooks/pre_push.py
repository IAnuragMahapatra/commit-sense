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


def _get_unpushed_commits(remote_sha: str) -> list[str]:
    """Get list of commit SHAs that haven't been pushed yet."""
    try:
        # Check if this is a new branch (remote SHA is all zeros)
        if remote_sha == "0" * 40:
            # New branch - get commits not reachable from any remote
            output = subprocess.check_output(
                ["git", "rev-list", "HEAD", "--not", "--remotes"],
                text=True,
            ).strip()
            return output.split("\n") if output else []

        # Get commits that are in HEAD but not in the remote SHA
        output = subprocess.check_output(
            ["git", "rev-list", f"{remote_sha}..HEAD"],
            text=True,
        ).strip()
        if not output:
            return []
        return output.split("\n")
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


def _rewrite_unpushed_commits(
    all_unpushed: list[str], fix_map: dict[str, str]
) -> tuple[str, dict[str, str]]:
    """
    Rewrite commit messages for unpushed commits using git plumbing.

    Args:
        all_unpushed: All unpushed SHAs, oldest-first
        fix_map: {sha: new_message} for commits that need fixing

    Returns:
        Tuple of (new_head_sha, old_to_new_mapping)
    """
    # Start from the parent of the oldest unpushed commit
    # Handle initial commit edge case (no parent)
    try:
        base = subprocess.check_output(
            ["git", "rev-parse", f"{all_unpushed[0]}^"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except subprocess.CalledProcessError:
        # Initial commit - no parent
        base = None

    new_parent = base
    old_to_new = {}

    for sha in all_unpushed:
        # Preserve original author metadata
        log_fmt = (
            subprocess.check_output(
                ["git", "log", "-1", "--pretty=%an%n%ae%n%aI%n%cn%n%ce%n%cI", sha],
                text=True,
            )
            .strip()
            .split("\n")
        )
        a_name, a_email, a_date, c_name, c_email, c_date = log_fmt

        # Get the tree (file contents) - unchanged
        tree = subprocess.check_output(
            ["git", "rev-parse", f"{sha}^{{tree}}"], text=True
        ).strip()

        # Use new message if in fix_map, otherwise keep original
        message = (
            fix_map.get(sha)
            or subprocess.check_output(
                ["git", "log", "-1", "--pretty=%B", sha], text=True
            ).strip()
        )

        # Set author/committer metadata
        env = {
            **os.environ,
            "GIT_AUTHOR_NAME": a_name,
            "GIT_AUTHOR_EMAIL": a_email,
            "GIT_AUTHOR_DATE": a_date,
            "GIT_COMMITTER_NAME": c_name,
            "GIT_COMMITTER_EMAIL": c_email,
            "GIT_COMMITTER_DATE": c_date,
        }

        # Create new commit object with same tree, new message, new parent
        if new_parent is None:
            # Initial commit - no parent
            commit_cmd = ["git", "commit-tree", tree, "-m", message]
        else:
            commit_cmd = ["git", "commit-tree", tree, "-p", new_parent, "-m", message]

        new_sha = subprocess.check_output(
            commit_cmd,
            text=True,
            env=env,
        ).strip()

        old_to_new[sha] = new_sha
        new_parent = new_sha

    return new_parent, old_to_new


def _post_to_dashboard(payload: dict, dashboard_cfg: dict) -> None:
    """POST a lightweight hook record to the dashboard. Never raises."""
    url = dashboard_cfg.get("url", "").rstrip("/")
    token = dashboard_cfg.get("token", "")

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


def _process_commit(sha: str) -> tuple[bool, str | None, str]:
    """
    Process a single commit. Returns (has_issues, rewritten_message, original_message).
    Does NOT amend - just checks and suggests rewrite.
    """
    _, message = _get_commit_info(sha)
    print(f"\n[CommitSense] {sha[:8]}")
    print(f"   Message: {message[:72]}")

    # 1. Git diff (no AST)
    try:
        file_diffs = get_diff(commit_ref=sha)
    except RuntimeError as exc:
        print(f"  ⚠ Diff failed: {exc} — skipping")
        return False, None, message

    if not file_diffs:
        print("  ✓ No file changes detected")
        return False, None, message

    # 2. Rule engine (empty ast_results — no AST in hook)
    flags = run_rules(message, file_diffs, ast_results={})
    score_data = compute_score(flags)

    if not flags:
        print(f"  ✓ Message looks good (grade {score_data['grade']})")
        return False, None, message

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
        print(f"  ⚠ Rewrite failed: {exc}")
        return True, None, message  # Has issues but can't suggest fix

    print("\n  📝 Suggested rewrite:")
    print(f"     Original:  {message}")
    print(f"     Rewritten: {result.rewritten}")
    print(f"     Reason:    {result.explanation}")

    return True, result.rewritten, message


def main() -> None:
    """Run the pre-push hook pipeline. Exits with 1 to block push if commits need fixing."""
    # Read stdin to get the refs being pushed
    # Format: <local ref> <local sha> <remote ref> <remote sha>
    stdin_input = sys.stdin.read().strip()

    # If no stdin (manual execution), check against current branch's upstream
    if not stdin_input:
        print("\n[CommitSense] Manual execution - checking against upstream")
        try:
            # Get the upstream of current branch
            remote_sha = subprocess.check_output(
                ["git", "rev-parse", "@{u}"],
                text=True,
                stderr=subprocess.DEVNULL,
            ).strip()
            unpushed = _get_unpushed_commits(remote_sha)
        except subprocess.CalledProcessError:
            print(
                "[CommitSense] No upstream branch set - cannot determine unpushed commits"
            )
            return
    else:
        # Parse stdin from git push - process ALL refs being pushed
        lines = stdin_input.split("\n")
        unpushed = []
        for line in lines:
            parts = line.split()
            if len(parts) < 4:
                continue

            _, _, _, remote_sha = parts[:4]
            unpushed.extend(_get_unpushed_commits(remote_sha))

        # Deduplicate while preserving order (branches can share commits)
        unpushed = list(dict.fromkeys(unpushed))

        # TODO: Multi-ref ordering issue - when pushing multiple branches,
        # commits from different branches get interleaved in undefined order
        # after extend+reverse. commit-tree then chains them sequentially as
        # if they were linear history, which is incorrect. For now, this works
        # for single-branch pushes (the common case).

        if not unpushed:
            print("\n[CommitSense] No refs to push")
            return

    if not unpushed:
        print("\n[CommitSense] All commits already pushed")
        return

    print(f"\n[CommitSense] Checking {len(unpushed)} unpushed commit(s)...")

    # Load config once for the entire run
    cfg = load_config()

    # Process commits from oldest to newest (reverse order)
    unpushed.reverse()

    commits_needing_fix = []
    for sha in unpushed:
        has_issues, rewritten_msg, original_msg = _process_commit(sha)

        if has_issues:
            commits_needing_fix.append((sha, rewritten_msg, original_msg))

    if not commits_needing_fix:
        print("\n[CommitSense] ✓ All commits look good")
        return

    # Check if auto_amend is enabled
    auto_amend = cfg.get("rewrite", {}).get("auto_amend", False)

    if not auto_amend:
        print("\n[CommitSense] ⚠ Push blocked - commits have quality issues")
        print("Set auto_amend: true in commitsense.yml to fix automatically")
        print("Or fix manually and commit again")
        sys.exit(1)

    # Auto-fix all commits with issues
    print(f"\n[CommitSense] ⚡ Auto-fixing {len(commits_needing_fix)} commit(s)...")

    # Create backup tag (force to handle collision from previous failed run)
    original_head = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], text=True
    ).strip()
    subprocess.run(
        ["git", "tag", "--force", "_commitsense_backup", original_head],
        check=True,
        capture_output=True,
    )

    try:
        # Build fix map: {sha: new_message}
        fix_map = {}
        for sha, rewritten_msg, original_msg in commits_needing_fix:
            if rewritten_msg:
                fix_map[sha] = rewritten_msg
            else:
                # Can't fix this commit - abort
                print(f"  ⚠ Could not generate rewrite for {sha[:8]}")
                raise RuntimeError("Missing rewrite for commit")

        # Rewrite all unpushed commits
        new_head, old_to_new = _rewrite_unpushed_commits(unpushed, fix_map)

        # Update HEAD to new commit chain
        subprocess.run(
            ["git", "reset", "--hard", new_head],
            check=True,
            capture_output=True,
            text=True,
        )

        print(f"  ✓ Rewrote {len(fix_map)} commit(s)")
        print(f"  ✓ New HEAD: {new_head[:8]}")

        # POST to dashboard for each fixed commit
        dashboard_cfg = cfg.get("dashboard", {})
        for sha, rewritten_msg, original_msg in commits_needing_fix:
            new_sha = old_to_new[sha]  # Use mapped new SHA
            _post_to_dashboard(
                {
                    "sha": new_sha,
                    "repo": _get_repo_name(),
                    "original_message": original_msg,
                    "rewritten_message": rewritten_msg,
                    "amended": True,
                },
                dashboard_cfg,
            )

        # Clean up backup tag
        subprocess.run(
            ["git", "tag", "-d", "_commitsense_backup"],
            capture_output=True,
        )

        print("\n[CommitSense] ✓ All commits fixed, push allowed")

    except Exception as exc:
        # Rollback on any error
        print(f"\n  ⚠ Rewrite failed: {exc}")
        print("  → Rolling back to original state...")
        subprocess.run(
            ["git", "reset", "--hard", original_head],
            capture_output=True,
        )
        subprocess.run(
            ["git", "tag", "-d", "_commitsense_backup"],
            capture_output=True,
        )
        print("  ✓ Rollback complete - no changes made")
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # Don't block push on internal errors - just warn
        print(f"  ⚠ CommitSense hook error: {exc}", file=sys.stderr)
        print("  → Allowing push (hook had internal error)", file=sys.stderr)
        sys.exit(0)  # Allow push despite hook error
