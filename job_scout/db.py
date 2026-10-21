import sqlite3
import json
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

from .config import DATA_DIR

DB_PATH = DATA_DIR / "jobs.db"

STATUSES = {
    "saved",
    "screened",
    "reviewing",
    "ready_for_review",
    "approved_by_human",
    "applied",
    "interview",
    "rejected",
    "closed"
}

def connect(db_path: Optional[Path] = None) -> sqlite3.Connection:
    target_path = db_path or DB_PATH
    target_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(target_path)
    con.row_factory = sqlite3.Row
    init_schema(con)
    return con

def init_schema(con: sqlite3.Connection):
    with con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                job_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                company TEXT NOT NULL,
                location TEXT,
                description TEXT,
                url TEXT,
                source TEXT,
                posted_date TEXT,
                eligible_countries TEXT,
                experience TEXT,
                salary TEXT DEFAULT '',
                score INTEGER DEFAULT 0,
                matched_skills TEXT DEFAULT '',
                role_match INTEGER DEFAULT 0,
                guardrail_passed INTEGER DEFAULT 1,
                guardrail_reason TEXT DEFAULT '',
                guardrail_flags TEXT DEFAULT '',
                ai_screened INTEGER DEFAULT 0,
                ai_score INTEGER DEFAULT 0,
                ai_verdict TEXT DEFAULT '',
                ai_analysis TEXT DEFAULT '',
                app_prep_status TEXT DEFAULT 'none',
                app_prep_dir TEXT DEFAULT '',
                status TEXT DEFAULT 'saved',
                human_notes TEXT DEFAULT '',
                first_seen TEXT,
                last_seen TEXT
            )
        """)
        # Safe column migrations in case DB was created earlier
        existing_cols = {row["name"] for row in con.execute("PRAGMA table_info(jobs)").fetchall()}
        columns_to_add = [
            ("salary", "TEXT DEFAULT ''"),
            ("guardrail_passed", "INTEGER DEFAULT 1"),
            ("guardrail_reason", "TEXT DEFAULT ''"),
            ("guardrail_flags", "TEXT DEFAULT ''"),
            ("ai_screened", "INTEGER DEFAULT 0"),
            ("ai_score", "INTEGER DEFAULT 0"),
            ("ai_verdict", "TEXT DEFAULT ''"),
            ("ai_analysis", "TEXT DEFAULT ''"),
            ("app_prep_status", "TEXT DEFAULT 'none'"),
            ("app_prep_dir", "TEXT DEFAULT ''"),
            ("human_notes", "TEXT DEFAULT ''")
        ]
        for col_name, col_def in columns_to_add:
            if col_name not in existing_cols:
                con.execute(f"ALTER TABLE jobs ADD COLUMN {col_name} {col_def}")

def upsert_job(con: sqlite3.Connection, job: Dict[str, Any]) -> bool:
    """
    Inserts a new job or updates an existing one without overwriting human statuses.
    Returns True if new, False if updated.
    """
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    job_id = job.get("job_id") or job.get("url")
    if not job_id or not job.get("title") or not job.get("company"):
        return False

    old = con.execute("SELECT job_id, status FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
    if old:
        con.execute("""
            UPDATE jobs SET
                title = ?, company = ?, location = ?, description = ?,
                url = ?, source = ?, posted_date = ?, eligible_countries = ?,
                experience = ?, salary = COALESCE(NULLIF(?, ''), salary),
                score = ?, matched_skills = ?, role_match = ?,
                guardrail_passed = ?, guardrail_reason = ?, guardrail_flags = ?,
                last_seen = ?
            WHERE job_id = ?
        """, (
            job.get("title", ""), job.get("company", ""), job.get("location", ""),
            job.get("description", ""), job.get("url", ""), job.get("source", ""),
            job.get("posted_date", ""), job.get("eligible_countries", ""),
            job.get("experience", ""), job.get("salary", ""),
            job.get("score", 0), job.get("matched_skills", ""),
            int(job.get("role_match", 0)),
            int(job.get("guardrail_passed", 1)),
            job.get("guardrail_reason", ""),
            job.get("guardrail_flags", ""),
            now, job_id
        ))
        return False
    else:
        con.execute("""
            INSERT INTO jobs (
                job_id, title, company, location, description, url, source,
                posted_date, eligible_countries, experience, salary, score,
                matched_skills, role_match, guardrail_passed, guardrail_reason,
                guardrail_flags, ai_screened, ai_score, ai_verdict, ai_analysis,
                app_prep_status, app_prep_dir, status, human_notes, first_seen, last_seen
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?,
                ?, ?, ?, ?,
                ?, 0, 0, '', '',
                'none', '', 'saved', '', ?, ?
            )
        """, (
            job_id, job.get("title", ""), job.get("company", ""), job.get("location", ""),
            job.get("description", ""), job.get("url", ""), job.get("source", ""),
            job.get("posted_date", ""), job.get("eligible_countries", ""),
            job.get("experience", ""), job.get("salary", ""), job.get("score", 0),
            job.get("matched_skills", ""), int(job.get("role_match", 0)),
            int(job.get("guardrail_passed", 1)), job.get("guardrail_reason", ""),
            job.get("guardrail_flags", ""), now, now
        ))
        return True

def update_guardrail(con: sqlite3.Connection, job_id: str, passed: bool, reason: str, flags: List[str]):
    with con:
        con.execute("""
            UPDATE jobs SET
                guardrail_passed = ?,
                guardrail_reason = ?,
                guardrail_flags = ?
            WHERE job_id = ?
        """, (int(passed), reason, ",".join(flags), job_id))

def update_ai_screen(con: sqlite3.Connection, job_id: str, ai_score: int, verdict: str, analysis: dict):
    with con:
        con.execute("""
            UPDATE jobs SET
                ai_screened = 1,
                ai_score = ?,
                ai_verdict = ?,
                ai_analysis = ?
            WHERE job_id = ?
        """, (ai_score, verdict, json.dumps(analysis, ensure_ascii=False), job_id))

def update_app_prep(con: sqlite3.Connection, job_id: str, prep_dir: str, status: str = "ready_for_review"):
    with con:
        con.execute("""
            UPDATE jobs SET
                app_prep_status = 'drafted',
                app_prep_dir = ?,
                status = ?
            WHERE job_id = ?
        """, (prep_dir, status, job_id))

def update_status(con: sqlite3.Connection, job_id: str, status: str, notes: Optional[str] = None):
    if status not in STATUSES:
        raise ValueError(f"Status '{status}' is invalid. Must be one of: {', '.join(sorted(STATUSES))}")
    with con:
        if notes is not None:
            con.execute("UPDATE jobs SET status = ?, human_notes = ? WHERE job_id = ?", (status, notes, job_id))
        else:
            con.execute("UPDATE jobs SET status = ? WHERE job_id = ?", (status, job_id))
