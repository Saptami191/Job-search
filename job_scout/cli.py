import argparse
import csv
import json
import re
import sys
import webbrowser
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Dict, Any

# Ensure UTF-8 output on Windows consoles
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from .config import (
    ROOT_DIR, DATA_DIR, OUTPUT_DIR, APPLICATIONS_DIR,
    load_config, load_candidate_profile, ensure_directories
)
from .db import (
    connect, upsert_job, update_guardrail, update_ai_screen,
    update_app_prep, update_status, STATUSES, DB_PATH
)
from .guardrails import evaluate_job
from .ai_agent import evaluate_job_match
from .application_prep import prepare_application_dossier
from .reporter import generate_reports
from .browser_agent import run_inspection

def norm(s):
    return re.sub(r"\s+", " ", str(s or "").lower()).strip()

def compute_keyword_score(row: Dict[str, Any], config: Dict[str, Any]):
    title = norm(row.get("title"))
    text = title + " " + norm(row.get("description"))
    
    req_skills = config.get("required_skills", [])
    pref_skills = config.get("preferred_skills", [])
    all_skills = req_skills + pref_skills
    
    matched = []
    for skill in all_skills:
        s = norm(skill)
        pattern = r"(?<![a-z0-9+#.])" + re.escape(s) + r"(?![a-z0-9+#.])"
        if re.search(pattern, text):
            matched.append(skill)
            
    roles = [norm(x) for x in config.get("target_titles", [])]
    role_match = any(role in title for role in roles)
    
    # Calculate score
    req_matched = [s for s in matched if s in req_skills]
    pref_matched = [s for s in matched if s in pref_skills]
    
    score = round((len(req_matched) / max(1, len(req_skills))) * 60 +
                  (len(pref_matched) / max(1, len(pref_skills))) * 30)
    if role_match:
        score = min(100, score + 10)
        
    return score, matched, role_match

def cmd_import(csv_path: str):
    config = load_config()
    path = Path(csv_path)
    if not path.is_absolute():
        path = ROOT_DIR / path
        
    if not path.exists():
        raise FileNotFoundError(f"CSV file not found: {path}")

    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    inserted = updated = guardrail_rejected = 0
    ensure_directories()
    
    with connect() as con:
        for raw_row in rows:
            row = {k.strip(): (v or "").strip() for k, v in raw_row.items() if k}
            job_id = row.get("job_id") or row.get("url")
            if not job_id or not row.get("title") or not row.get("company"):
                continue

            row["job_id"] = job_id
            
            # 1. Guardrail evaluation
            guardrail_res = evaluate_job(row, config)
            row["guardrail_passed"] = 1 if guardrail_res["eligible"] else 0
            row["guardrail_reason"] = guardrail_res["reason"]
            row["guardrail_flags"] = ",".join(guardrail_res.get("flags", []))
            
            if not guardrail_res["eligible"]:
                guardrail_rejected += 1

            # 2. Keyword relevance scoring
            score, matched, role_match = compute_keyword_score(row, config)
            row["score"] = score
            row["matched_skills"] = ", ".join(matched)
            row["role_match"] = int(role_match)

            is_new = upsert_job(con, row)
            if is_new:
                inserted += 1
            else:
                updated += 1
                
    print(f"\n Import Complete:")
    print(f"   * {inserted} new jobs added")
    print(f"   * {updated} existing jobs updated")
    print(f"   * {guardrail_rejected} jobs flagged/filtered by screening guardrails")
    print(f"   * SQLite DB: {DB_PATH}\n")

def cmd_guardrail():
    config = load_config()
    with connect() as con:
        rows = [dict(r) for r in con.execute("SELECT * FROM jobs").fetchall()]
        passed = failed = 0
        for r in rows:
            res = evaluate_job(r, config)
            update_guardrail(con, r["job_id"], res["eligible"], res["reason"], res["flags"])
            if res["eligible"]:
                passed += 1
            else:
                failed += 1
    print(f"\n Guardrails Re-evaluated:")
    print(f"   * {passed} passed (eligible for AI review)")
    print(f"   * {failed} rejected (excluded by guardrails)\n")

def cmd_ai_screen(limit: int = 10, job_id: str = None):
    config = load_config()
    with connect() as con:
        if job_id:
            rows = [dict(r) for r in con.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchall()]
        else:
            rows = [dict(r) for r in con.execute("""
                SELECT * FROM jobs
                WHERE guardrail_passed = 1 AND (ai_screened = 0 OR ai_score = 0)
                ORDER BY score DESC LIMIT ?
            """, (limit,)).fetchall()]

    if not rows:
        print("No jobs pending AI screening. Use --all or import new jobs.")
        return

    print(f"\n Starting AI Screening for {len(rows)} role(s)...")
    with connect() as con:
        for i, row in enumerate(rows, 1):
            print(f"[{i}/{len(rows)}] Evaluating: {row['title']} @ {row['company']}...")
            analysis = evaluate_job_match(row)
            ai_score = analysis.get("score", row["score"])
            verdict = analysis.get("verdict", "BORDERLINE")
            update_ai_screen(con, row["job_id"], ai_score, verdict, analysis)
            print(f"      -> Verdict: {verdict} | AI Fit Score: {ai_score}/100")
            print(f"      -> Summary: {analysis.get('summary', '')}")
    print("\nAI Screening Complete.\n")

def cmd_prep(job_id: str):
    with connect() as con:
        row = con.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
        if not row:
            print(f"Job ID '{job_id}' not found.")
            return
        job = dict(row)

    ai_analysis = {}
    if job.get("ai_analysis"):
        try:
            ai_analysis = json.loads(job["ai_analysis"])
        except Exception:
            pass
    if not ai_analysis:
        ai_analysis = evaluate_job_match(job)

    dest_dir = prepare_application_dossier(job, ai_analysis)
    with connect() as con:
        update_app_prep(con, job_id, str(dest_dir.relative_to(ROOT_DIR)), "ready_for_review")

    print(f"\n Application Package Prepared for Human Review:")
    print(f"   * Role: {job['title']} @ {job['company']}")
    print(f"   * Location: {job['location']}")
    print(f"   * Official Link: {job['url']}")
    print(f"   * Review Dossier: {dest_dir}")
    print(f"      - Tailored Resume: {dest_dir / 'tailored_resume.md'}")
    print(f"      - Screening Answers: {dest_dir / 'screening_answers.md'}")
    print(f"      - Approval Checklist: {dest_dir / 'approval_checklist.md'}")
    print(f"\n  Human Approval Gate: Please review the files in that folder, then submit via the official portal.\n")

def cmd_prep_top(limit: int = 3):
    with connect() as con:
        rows = con.execute("""
            SELECT job_id FROM jobs
            WHERE guardrail_passed = 1 AND app_prep_status = 'none'
            ORDER BY COALESCE(NULLIF(ai_score, 0), score) DESC
            LIMIT ?
        """, (limit,)).fetchall()
    
    if not rows:
        print("No eligible jobs pending application prep.")
        return
    for r in rows:
        cmd_prep(r["job_id"])

def cmd_report(limit: int = 30, include_unknown: bool = False):
    res = generate_reports(limit=limit, include_unknown=include_unknown)
    print(f"\n Ranked Job Shortlist Generated ({res['count']} jobs):")
    print(f"   * Excel Report: {res['xlsx']}")
    print(f"   * CSV Shortlist: {res['csv']}\n")

    # Terminal preview
    with connect() as con:
        rows = [dict(r) for r in con.execute("""
            SELECT job_id, title, company, location, score, ai_score, ai_verdict, status
            FROM jobs
            WHERE guardrail_passed = 1
            ORDER BY COALESCE(NULLIF(ai_score, 0), score) DESC
            LIMIT ?
        """, (min(10, limit),)).fetchall()]

    for i, r in enumerate(rows, 1):
        effective = r["ai_score"] or r["score"] or 0
        verdict = r["ai_verdict"] or "RECOMMENDED"
        print(f"{i:>2}. [{effective:>3}/100] {r['title']} — {r['company']}")
        print(f"    Location: {r['location']} | Verdict: {verdict} | Status: {r['status']}")
        print(f"    ID: {r['job_id']}\n")

def cmd_status(job_id: str, status: str, notes: str = None):
    with connect() as con:
        update_status(con, job_id, status, notes)
    print(f" Updated job '{job_id}' status to '{status}'.")

def cmd_open(limit: int = 5):
    with connect() as con:
        rows = con.execute("""
            SELECT url, title, company FROM jobs
            WHERE status IN ('saved', 'screened', 'reviewing', 'ready_for_review')
            ORDER BY COALESCE(NULLIF(ai_score, 0), score) DESC
            LIMIT ?
        """, (limit,)).fetchall()
    for r in rows:
        url = r["url"] or ""
        if url.startswith(("http://", "https://")):
            print(f"Opening: {r['title']} — {r['company']} ({url})")
            webbrowser.open_new_tab(url)

def cmd_inspect(url: str):
    print(f"\n Inspecting job listing at {url} (Strictly Read-Only)...")
    res = run_inspection(url)
    print("\n--- Structured Inspection Output ---")
    print(json.dumps(res, indent=2))

def cmd_daily():
    print("=" * 60)
    print(" DAILY JOB SCOUT RUNNER - TITHI'S BACKEND & INFRA SEARCH")
    print("=" * 60)
    print("\n1. Importing new listings from jobs.csv...")
    cmd_import("jobs.csv")

    print("\n2. Re-verifying guardrails...")
    cmd_guardrail()

    print("\n3. Running AI screening on top candidate listings...")
    cmd_ai_screen(limit=5)

    print("\n4. Prepping application dossiers for top 3 matching roles...")
    cmd_prep_top(limit=3)

    print("\n5. Generating ranked Excel & CSV reports...")
    cmd_report(limit=30, include_unknown=True)

    print("=" * 60)
    print(" Daily run complete! Open output/ranked_jobs.xlsx to review.")
    print("=" * 60)

def main():
    parser = argparse.ArgumentParser(description="Local AI Job Scout & Application Prep Agent")
    sub = parser.add_subparsers(dest="command", required=True)

    # import
    p_imp = sub.add_parser("import", help="Import jobs from CSV")
    p_imp.add_argument("csv_path", nargs="?", default="jobs.csv")

    # guardrail
    sub.add_parser("guardrail", help="Re-run screening guardrails")

    # ai-screen
    p_screen = sub.add_parser("ai-screen", help="Run AI matching on guardrail-passed jobs")
    p_screen.add_argument("--limit", type=int, default=10)
    p_screen.add_argument("--job-id", type=str, default=None)

    # prep
    p_prep = sub.add_parser("prep", help="Prepare tailored resume, Q&A draft and checklist for a job")
    p_prep.add_argument("job_id", type=str)

    # prep-top
    p_preptop = sub.add_parser("prep-top", help="Prepare application dossiers for top N jobs")
    p_preptop.add_argument("--limit", type=int, default=3)

    # report
    p_rep = sub.add_parser("report", help="Generate Excel and CSV shortlist reports")
    p_rep.add_argument("--limit", type=int, default=30)
    p_rep.add_argument("--include-unknown", action="store_true")

    # status
    p_stat = sub.add_parser("status", help="Update job application status")
    p_stat.add_argument("job_id", type=str)
    p_stat.add_argument("status", choices=sorted(STATUSES))
    p_stat.add_argument("--notes", type=str, default=None)

    # open
    p_open = sub.add_parser("open", help="Open top active job links in browser")
    p_open.add_argument("--limit", type=int, default=5)

    # inspect-url
    p_ins = sub.add_parser("inspect-url", help="Inspect a job listing URL with browser agent")
    p_ins.add_argument("url", type=str)

    # daily
    sub.add_parser("daily", help="Run complete daily workflow (import, guardrails, screen, prep, report)")

    args = parser.parse_args()
    try:
        if args.command == "import":
            cmd_import(args.csv_path)
        elif args.command == "guardrail":
            cmd_guardrail()
        elif args.command == "ai-screen":
            cmd_ai_screen(limit=args.limit, job_id=args.job_id)
        elif args.command == "prep":
            cmd_prep(args.job_id)
        elif args.command == "prep-top":
            cmd_prep_top(limit=args.limit)
        elif args.command == "report":
            cmd_report(limit=args.limit, include_unknown=args.include_unknown)
        elif args.command == "status":
            cmd_status(args.job_id, args.status, getattr(args, "notes", None))
        elif args.command == "open":
            cmd_open(limit=args.limit)
        elif args.command == "inspect-url":
            cmd_inspect(args.url)
        elif args.command == "daily":
            cmd_daily()
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
