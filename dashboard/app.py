"""FastAPI dashboard — receives reports from CI/hook, serves commit history and trends."""

import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel
from dotenv import load_dotenv

from dashboard.database import engine, get_db
from dashboard.models import Base, Repo, Commit, Flag

load_dotenv()

@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Create DB tables on startup."""
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="CommitSense Dashboard", lifespan=lifespan)

DASHBOARD_TOKEN = os.environ.get("DASHBOARD_TOKEN", "")


# ── Auth ──────────────────────────────────────────────────

def verify_token(authorization: str = Header(...)):
    if not DASHBOARD_TOKEN:
        return  # token not configured — open access (dev mode)
    scheme, _, token = authorization.partition(" ")
    if token != DASHBOARD_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid token")


# ── Request schemas ───────────────────────────────────────

class FlagSchema(BaseModel):
    rule: str
    severity: str
    detail: str | None = None


class ReportPayload(BaseModel):
    sha: str
    repo: str
    original_message: str | None = None
    rewritten_message: str | None = None
    amended: bool = False
    score: int | None = None
    grade: str | None = None
    llm_aligned: bool | None = None
    llm_reason: str | None = None
    flags: list[FlagSchema] = []


# ── Endpoints ─────────────────────────────────────────────

@app.post("/api/reports", dependencies=[Depends(verify_token)])
def post_report(payload: ReportPayload, db: Session = Depends(get_db)):
    """Upsert a report from CI or pre-push hook."""
    # Get or create repo
    repo = db.query(Repo).filter(Repo.name == payload.repo).first()
    if not repo:
        repo = Repo(name=payload.repo)
        db.add(repo)
        db.flush()

    # Upsert commit on sha — merge hook + CI payloads
    commit = db.query(Commit).filter(Commit.sha == payload.sha).first()
    if not commit:
        commit = Commit(sha=payload.sha, repo_id=repo.id)
        db.add(commit)

    # Merge fields — only overwrite if incoming value is not None
    for field in ("original_message", "rewritten_message", "amended",
                  "score", "grade", "llm_aligned", "llm_reason"):
        value = getattr(payload, field)
        if value is not None:
            setattr(commit, field, value)

    db.flush()

    # Replace flags if any provided (CI provides the full set)
    if payload.flags:
        db.query(Flag).filter(Flag.commit_id == commit.id).delete()
        for f in payload.flags:
            db.add(Flag(commit_id=commit.id, rule=f.rule,
                        severity=f.severity, detail=f.detail))

    db.commit()
    return {"status": "ok", "sha": payload.sha}


@app.get("/api/repos")
def get_repos(db: Session = Depends(get_db)):
    """List all tracked repositories."""
    repos = db.query(Repo).all()
    return [{"id": r.id, "name": r.name, "created_at": r.created_at} for r in repos]


@app.get("/api/repos/{repo}/commits")
def get_commits(repo: str, limit: int = 50, db: Session = Depends(get_db)):
    """List commits for a repo, most recent first."""
    repo_obj = db.query(Repo).filter(Repo.name == repo).first()
    if not repo_obj:
        raise HTTPException(status_code=404, detail="Repo not found")

    commits = (
        db.query(Commit)
        .filter(Commit.repo_id == repo_obj.id)
        .order_by(Commit.created_at.desc())
        .limit(limit)
        .all()
    )
    return [_commit_dict(c) for c in commits]


@app.get("/api/repos/{repo}/trends")
def get_trends(repo: str, db: Session = Depends(get_db)):
    """Grade distribution and average score over time."""
    repo_obj = db.query(Repo).filter(Repo.name == repo).first()
    if not repo_obj:
        raise HTTPException(status_code=404, detail="Repo not found")

    rows = (
        db.query(Commit.grade, func.count(Commit.id).label("count"))
        .filter(Commit.repo_id == repo_obj.id, Commit.grade.isnot(None))
        .group_by(Commit.grade)
        .all()
    )
    avg = (
        db.query(func.avg(Commit.score))
        .filter(Commit.repo_id == repo_obj.id, Commit.score.isnot(None))
        .scalar()
    )
    return {
        "grade_distribution": {row.grade: row.count for row in rows},
        "average_score": round(avg, 2) if avg is not None else None,
    }


@app.get("/api/repos/{repo}/patterns")
def get_patterns(repo: str, db: Session = Depends(get_db)):
    """Most frequently triggered rules across all commits."""
    repo_obj = db.query(Repo).filter(Repo.name == repo).first()
    if not repo_obj:
        raise HTTPException(status_code=404, detail="Repo not found")

    rows = (
        db.query(Flag.rule, Flag.severity, func.count(Flag.id).label("count"))
        .join(Commit)
        .filter(Commit.repo_id == repo_obj.id)
        .group_by(Flag.rule, Flag.severity)
        .order_by(func.count(Flag.id).desc())
        .limit(10)
        .all()
    )
    return [{"rule": r.rule, "severity": r.severity, "count": r.count} for r in rows]


# ── Helpers ───────────────────────────────────────────────

def _commit_dict(c: Commit) -> dict:
    return {
        "sha": c.sha,
        "original_message": c.original_message,
        "rewritten_message": c.rewritten_message,
        "amended": c.amended,
        "score": c.score,
        "grade": c.grade,
        "llm_aligned": c.llm_aligned,
        "llm_reason": c.llm_reason,
        "created_at": c.created_at,
        "flags": [
            {"rule": f.rule, "severity": f.severity, "detail": f.detail}
            for f in c.flags
        ],
    }
