import csv
import json
import re
from pathlib import Path
from typing import List, Dict, Any

from .guardrails import evaluate_job
from .config import load_config

def parse_csv_listings(file_path: Path) -> List[Dict[str, Any]]:
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    
    with file_path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        jobs = []
        for row in reader:
            clean = {k.strip(): (v or "").strip() for k, v in row.items() if k}
            if clean.get("title") and clean.get("company"):
                if not clean.get("job_id"):
                    clean["job_id"] = clean.get("url") or f"{clean['company']}-{clean['title']}".lower()
                jobs.append(clean)
        return jobs

def parse_pasted_alert_text(text: str, source: str = "Alert") -> List[Dict[str, Any]]:
    """
    Parses pasted text from LinkedIn or Naukri daily job alert notifications.
    Matches lines formatted like:
    [Role Title] at [Company] - [Location] - [URL]
    or blocks with Title / Company / Location / Link.
    """
    jobs = []
    blocks = re.split(r"\n\s*\n", text.strip())
    config = load_config()

    for idx, block in enumerate(blocks, 1):
        lines = [l.strip() for l in block.splitlines() if l.strip()]
        if not lines:
            continue
        
        title = lines[0]
        company = lines[1] if len(lines) > 1 else "Unknown"
        location = lines[2] if len(lines) > 2 else "Remote India"
        url = ""
        desc = ""
        
        for l in lines[2:]:
            if l.startswith("http"):
                url = l
            else:
                desc += " " + l

        job_id = f"{re.sub(r'[^a-zA-Z0-9]', '', company).lower()}-{re.sub(r'[^a-zA-Z0-9]', '', title).lower()}-{idx}"
        jobs.append({
            "job_id": job_id,
            "title": title,
            "company": company,
            "location": location,
            "description": desc.strip() or f"{title} role at {company}",
            "url": url,
            "source": source,
            "posted_date": "",
            "eligible_countries": "India",
            "experience": "0-2 years"
        })
    return jobs
