"""Rewriter — LLM-powered commit message rewrite for the pre-push hook."""

import json
from dataclasses import dataclass

from llm.adapter import complete
from rules.engine import Flag

SYSTEM_PROMPT = """\
You are a Git commit message editor. Your only job is to rewrite a bad commit \
message into a good one.

Rules:
- Follow conventional commits exactly: type(scope): subject
- Valid types: feat, fix, docs, style, refactor, perf, test, chore, ci, build, revert
- Subject must be imperative mood, lowercase, no trailing period
- Subject must be concise (50 chars or fewer)
- If the diff mentions a breaking change, add ! after type(scope)
- Do not invent details not supported by the diff

Respond with a JSON object only — no markdown, no extra text:
{
  "rewritten": "<conventional commit message>",
  "explanation": "<one sentence: what was wrong and what you changed>"
}"""


@dataclass
class RewriteResult:
    rewritten: str
    explanation: str


def rewrite_message(
    original_message: str,
    flags: list[Flag],
    diff_summary: str,
) -> RewriteResult:
    """
    Rewrite a commit message using the LLM.

    Args:
        original_message: The original (bad) commit message.
        flags:            Rule flags that fired for this commit.
        diff_summary:     A short diff summary (file names + sample lines).

    Returns:
        RewriteResult with rewritten message and a one-sentence explanation.

    Raises:
        RuntimeError: If the LLM call fails or returns unparseable output.
    """
    flag_lines = "\n".join(
        f"- [{f.severity.upper()}] {f.rule}: {f.detail}" for f in flags
    ) or "- (no rule flags)"

    # Cap diff summary to keep prompt short
    diff_lines = diff_summary.splitlines()[:60]
    diff_text = "\n".join(diff_lines)

    user_content = (
        f"Original message:\n{original_message}\n\n"
        f"Rule violations:\n{flag_lines}\n\n"
        f"Diff summary:\n{diff_text}"
    )

    try:
        raw = complete(
            [{"role": "user", "content": user_content}],
            system_prompt=SYSTEM_PROMPT,
        )
        raw = raw.strip().strip("```json").strip("```").strip()
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Rewriter: LLM returned non-JSON output — {exc}") from exc
    except Exception as exc:
        raise RuntimeError(f"Rewriter: LLM call failed — {exc}") from exc

    rewritten = data.get("rewritten", "").strip()
    explanation = data.get("explanation", "").strip()

    if not rewritten:
        raise RuntimeError("Rewriter: LLM returned empty 'rewritten' field")

    return RewriteResult(rewritten=rewritten, explanation=explanation)
