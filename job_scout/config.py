from pathlib import Path
import json
import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

PACKAGE_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = Path(os.getenv("JOB_SCOUT_HOME", Path.cwd())).expanduser().resolve()
CONFIG_PATH = ROOT_DIR / "config.json"
DATA_DIR = ROOT_DIR / "data"
OUTPUT_DIR = ROOT_DIR / "output"
APPLICATIONS_DIR = OUTPUT_DIR / "applications"
PROFILE_PATH = ROOT_DIR / "candidate_profile.json"
ENV_PATH = ROOT_DIR / ".env"

DEFAULT_CONFIG = {
    "target_titles": [
        "Backend Engineer",
        "Software Engineer",
        "Platform Engineer",
        "Infrastructure Engineer",
        "API Engineer",
        "AI Infrastructure Engineer",
        "Founding Engineer"
    ],
    "candidate_location": "India",
    "remote_preferences": [
        "Remote India",
        "Worldwide remote"
    ],
    "employment_types": [
        "Internship",
        "Full-time",
        "Graduate"
    ],
    "experience_max_years": 2,
    "required_skills": [
        "Python",
        "Node.js",
        "C++",
        "SQL",
        "PostgreSQL",
        "Docker",
        "REST APIs"
    ],
    "preferred_skills": [
        "Distributed systems",
        "AWS",
        "GCP",
        "FastAPI",
        "Kubernetes",
        "Redis"
    ],
    "avoid_keywords": [
        "Unpaid",
        "Senior",
        "Staff Engineer",
        "Principal Engineer",
        "Lead",
        "Architect",
        "Manager"
    ],
    "eligible_country_terms": [
        "india",
        "worldwide",
        "global remote",
        "anywhere",
        "remote"
    ],
    "minimum_score": 15,
    "require_india_eligibility": True,
    "require_human_approval_before_submit": True,
    "llm_provider": "openai",
    "llm_model": "gpt-4o"
}

def load_config() -> dict:
    config = DEFAULT_CONFIG.copy()
    if CONFIG_PATH.exists():
        try:
            with CONFIG_PATH.open(encoding="utf-8") as f:
                user_cfg = json.load(f)
                config.update(user_cfg)
        except Exception as e:
            print(f"[Warning] Failed to parse config.json ({e}), using defaults.")
    return config

def load_candidate_profile() -> dict:
    if PROFILE_PATH.exists():
        try:
            with PROFILE_PATH.open(encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[Warning] Failed to parse candidate_profile.json ({e}).")
    return {}

def ensure_directories():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    APPLICATIONS_DIR.mkdir(parents=True, exist_ok=True)
