"""CLI stdout reporter — prints full analysis results without needing the dashboard."""


GRADE_COLORS = {"A": "✅", "B": "🟡", "C": "🟠", "D": "🔴"}
SEVERITY_ICONS = {"info": "ℹ", "warning": "⚠", "critical": "✖"}


def print_report(report: dict) -> None:
    """Pretty-print a full analysis report to stdout."""
    grade = report.get("grade", "?")
    score = report.get("score", 0)
    sha = report.get("sha", "")[:8]
    message = report.get("original_message", "")
    flags = report.get("flags", [])
    llm_aligned = report.get("llm_aligned")
    llm_reason = report.get("reason") or report.get("llm_reason", "")

    icon = GRADE_COLORS.get(grade, "")

    print()
    print("━" * 60)
    print(f"  CommitSense Report  {icon} Grade {grade}  (score: {score})")
    print("━" * 60)
    print(f"  Commit : {sha}")
    print(f"  Message: {message}")
    print()

    if flags:
        print("  Flags:")
        for f in flags:
            icon_f = SEVERITY_ICONS.get(f["severity"] if isinstance(f, dict) else f.severity, "•")
            rule = f["rule"] if isinstance(f, dict) else f.rule
            detail = f["detail"] if isinstance(f, dict) else f.detail
            sev = f["severity"] if isinstance(f, dict) else f.severity
            print(f"    {icon_f} [{sev.upper():8}] {rule}: {detail}")
    else:
        print("  Flags : none — clean commit")

    print()
    if llm_aligned is None:
        print("  LLM   : skipped or failed")
    elif llm_aligned:
        print(f"  LLM   : ✅ aligned — {llm_reason}")
    else:
        print(f"  LLM   : ❌ not aligned — {llm_reason}")

    print("━" * 60)
    print()
