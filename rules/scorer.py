"""Scorer — converts rule engine flags into a numeric score and letter grade."""

from rules.engine import Flag

SEVERITY_POINTS = {"info": 1, "warning": 3, "critical": 7}


def compute_score(flags: list[Flag]) -> dict:
    """
    Compute a score and grade from a list of flags.

    Scoring:
        info     = 1 pt
        warning  = 3 pts
        critical = 7 pts

    Grading:
        A  — 0 pts
        B  — 1–5 pts
        C  — 6–12 pts
        D  — 13+ pts

    Returns:
        {"score": int, "grade": str}
    """
    score = sum(SEVERITY_POINTS.get(f.severity, 0) for f in flags)

    if score == 0:
        grade = "A"
    elif score <= 5:
        grade = "B"
    elif score <= 12:
        grade = "C"
    else:
        grade = "D"

    return {"score": score, "grade": grade}
