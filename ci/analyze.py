"""CI analysis runner — full pipeline: diff → AST → rules → LLM → POST to dashboard."""

import json
import os
import subprocess
import sys

import requests

from cli.reporter import print_report
from diff.ast_extractor import extract_definitions
from diff.parser import get_diff
from llm.adapter import complete
from llm.config import load_config
from rules.engine import run_rules
from rules.scorer import compute_score

SYSTEM_PROMPT = """You are a commit quality validator. Assess if the commit message accurately describes the code changes.

CRITICAL: Only consider the rule violations explicitly listed below. Do NOT invent or mention rules that are not present.

Your response MUST be valid JSON with this exact structure:
{
  "aligned": true,
  "reason": "brief explanation"
}

Set aligned to false only if:
1. The message contradicts the actual changes in the diff
2. The message is too vague to understand what changed
3. Critical rule violations make the message unusable

Set aligned to true if the message reasonably describes what changed, even if it has minor formatting issues."""


def get_commit_info(commit_ref: str = "HEAD") -> tuple[str, str]:
    """Return (sha, commit_message) for the given commit reference."""
    sha = subprocess.check_output(
        ["git", "rev-parse", commit_ref], text=True, encoding="utf-8", errors="replace"
    ).strip()
    message = subprocess.check_output(
        ["git", "log", "-1", "--pretty=%B", commit_ref],
        text=True,
        encoding="utf-8",
        errors="replace",
    ).strip()
    return sha, message


def build_diff_summary(file_diffs) -> str:
    """Produce a concise diff summary for the LLM context."""
    lines = []
    for fd in file_diffs:
        lines.append(f"File: {fd.path} (+{fd.additions}/-{fd.deletions})")
        for hunk in fd.hunks[:2]:  # first 2 hunks only to keep prompt short
            for line in hunk.lines[:10]:
                lines.append(f"  {line}")
    return "\n".join(lines[:80])  # hard cap at 80 lines


def validate_with_llm(message: str, diff_summary: str, flags: list) -> dict:
    """Ask the LLM whether the message aligns with the diff."""
    flag_lines = (
        "\n".join(f"- [{f.severity.upper()}] {f.rule}: {f.detail}" for f in flags)
        if flags
        else "- (no rule violations)"
    )

    user_content = (
        f"Commit message:\n{message}\n\n"
        f"Rule violations:\n{flag_lines}\n\n"
        f"Diff summary:\n{diff_summary}"
    )
    try:
        raw = complete(
            [{"role": "user", "content": user_content}],
            system_prompt=SYSTEM_PROMPT,
        )
        # Strip markdown fences if present
        raw = raw.strip().strip("```json").strip("```").strip()
        return json.loads(raw)
    except Exception as exc:
        return {"aligned": None, "reason": f"LLM call failed: {exc}"}


def post_to_dashboard(payload: dict) -> None:
    """POST the full report to the dashboard."""
    cfg = load_config()
    dashboard = cfg.get("dashboard", {})
    url = dashboard.get("url", "").rstrip("/")
    token = dashboard.get("token", "")

    if not url:
        print("[ci] No dashboard URL configured — skipping POST")
        return

    try:
        resp = requests.post(
            f"{url}/api/reports",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        resp.raise_for_status()
        print(f"[ci] Report posted — status {resp.status_code}")
    except Exception as exc:
        print(f"[ci] Dashboard POST failed: {exc}", file=sys.stderr)


def run(repo_path: str = ".", commit_ref: str = "HEAD") -> dict:
    """Run the full CI analysis pipeline. Returns the report dict."""
    sha, message = get_commit_info(commit_ref)
    print(f"[ci] Analyzing commit {sha[:8]}: {message[:60]}")

    # 1. Git diff
    file_diffs = get_diff(repo_path, commit_ref)
    print(f"[ci] {len(file_diffs)} file(s) changed")

    # 2. AST extraction (changed files only, supported extensions)
    supported = {".py", ".js", ".mjs", ".cjs", ".ts", ".tsx"}
    ast_results = {}
    for fd in file_diffs:
        if any(fd.path.endswith(ext) for ext in supported):
            ast_results[fd.path] = extract_definitions(fd.path, repo_path)

    # 3. Rule engine
    flags = run_rules(message, file_diffs, ast_results)
    score_data = compute_score(flags)
    print(f"[ci] Grade: {score_data['grade']}  Score: {score_data['score']}")

    # 4. LLM validation
    diff_summary = build_diff_summary(file_diffs)
    llm_result = validate_with_llm(message, diff_summary, flags)
    print(
        f"[ci] LLM aligned: {llm_result.get('aligned')} — {llm_result.get('reason', '')}"
    )

    # 5. Build report
    repo = (
        subprocess.check_output(
            ["git", "remote", "get-url", "origin"],
            text=True,
            encoding="utf-8",
            errors="replace",
        ).strip()
        if _has_remote()
        else os.path.basename(os.path.abspath(repo_path))
    )

    report = {
        "sha": sha,
        "repo": repo,
        "original_message": message,
        "rewritten_message": None,
        "amended": False,
        "score": score_data["score"],
        "grade": score_data["grade"],
        "llm_aligned": llm_result.get("aligned"),
        "llm_reason": llm_result.get("reason"),
        "flags": [
            {"rule": f.rule, "severity": f.severity, "detail": f.detail} for f in flags
        ],
    }

    return report


def _has_remote() -> bool:
    try:
        subprocess.check_output(
            ["git", "remote", "get-url", "origin"], stderr=subprocess.DEVNULL
        )
        return True
    except subprocess.CalledProcessError:
        return False


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Analyze a commit with CommitSense")
    parser.add_argument(
        "commit",
        nargs="?",
        default="HEAD",
        help="Commit SHA or reference (default: HEAD)",
    )
    parser.add_argument(
        "--repo", default=".", help="Repository path (default: current directory)"
    )
    args = parser.parse_args()

    try:
        report = run(repo_path=args.repo, commit_ref=args.commit)
        print_report(report)
        post_to_dashboard(report)
    except Exception as exc:
        print(f"[ci] Fatal error: {exc}", file=sys.stderr)
        sys.exit(1)
