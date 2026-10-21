import re
from typing import Dict, Any, List

INDIA_TECH_HUBS = {
    "india", "bengaluru", "bangalore", "hyderabad", "pune", "mumbai",
    "delhi", "gurgaon", "gurugram", "noida", "chennai", "kolkata",
    "ahmedabad", "kochi", "coimbatore"
}

REMOTE_TERMS = {
    "remote", "work from home", "wfh", "worldwide", "global remote",
    "anywhere", "telecommute"
}

def evaluate_job(job: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Deterministic rule-based screening guardrail.
    Filters out obvious mismatches without invoking an LLM.
    Returns:
        {
            "eligible": bool,
            "reason": str,
            "flags": List[str],
            "uncertainties": List[str]
        }
    """
    title = str(job.get("title") or "").strip().lower()
    description = str(job.get("description") or "").strip().lower()
    location = str(job.get("location") or "").strip().lower()
    eligible_countries = str(job.get("eligible_countries") or "").strip().lower()
    experience_raw = str(job.get("experience") or "").strip().lower()
    full_text = f"{title} {description} {location} {experience_raw}"

    flags: List[str] = []
    uncertainties: List[str] = []

    # 1. Reject explicit exclusion keywords in title
    avoid_keywords = config.get("avoid_keywords", ["unpaid", "senior", "staff engineer", "principal engineer"])
    for word in avoid_keywords:
        w_lower = word.lower()
        # Word boundary match to avoid substring false positives
        pattern = r"(?<![a-z0-9])" + re.escape(w_lower) + r"(?![a-z0-9])"
        if re.search(pattern, title):
            return {
                "eligible": False,
                "reason": f"Excluded title keyword: {word}",
                "flags": [f"avoid_keyword_{word}"],
                "uncertainties": []
            }

    # 2. Reject explicit unpaid roles in title or description
    if re.search(r"\b(unpaid|without pay|stipend\s*:\s*(?:nil|none|0))\b", full_text):
        return {
            "eligible": False,
            "reason": "Unpaid opportunity rejected by preferences",
            "flags": ["unpaid_role"],
            "uncertainties": []
        }

    # 3. Location and Work Authorization Verification
    candidate_loc = config.get("candidate_location", "India").lower()
    require_india = config.get("require_india_eligibility", True)

    is_remote = any(term in location for term in REMOTE_TERMS) or any(term in eligible_countries for term in REMOTE_TERMS)
    is_india_local = any(hub in location for hub in INDIA_TECH_HUBS) or "india" in eligible_countries

    if require_india:
        # Check if country restrictions explicitly exclude India
        us_only_terms = ["us only", "usa only", "north america only", "must be located in the us", "us citizenship required", "emea only", "uk only"]
        if any(term in full_text for term in us_only_terms):
            return {
                "eligible": False,
                "reason": "Restricted to specific foreign region (e.g., US/UK/EMEA only)",
                "flags": ["region_restricted"],
                "uncertainties": []
            }

        if not is_remote and not is_india_local:
            if not location or location in ["unknown", "unspecified"]:
                uncertainties.append("Location unspecified; requires confirmation")
            else:
                return {
                    "eligible": False,
                    "reason": f"Location '{location}' is not India or established Remote",
                    "flags": ["incompatible_location"],
                    "uncertainties": []
                }

    # 4. Experience Upper Bound Check (Avoid over-senior roles)
    max_years = config.get("experience_max_years", 2)
    
    # Check explicitly in title first
    title_exp_match = re.search(r"(\d+)\+?\s*(?:to\s*(\d+))?\s*(?:years|yrs|yoe)", title)
    if title_exp_match:
        min_exp = int(title_exp_match.group(1))
        if min_exp > max_years:
            return {
                "eligible": False,
                "reason": f"Required experience ({min_exp}+ years in title) exceeds candidate maximum of {max_years} years",
                "flags": ["experience_exceeded"],
                "uncertainties": []
            }

    # Check experience field if populated
    if experience_raw and experience_raw != "unknown":
        exp_match = re.search(r"(\d+)\+?", experience_raw)
        if exp_match:
            min_exp = int(exp_match.group(1))
            if min_exp > max_years:
                return {
                    "eligible": False,
                    "reason": f"Experience requirement '{experience_raw}' exceeds maximum of {max_years} years",
                    "flags": ["experience_exceeded"],
                    "uncertainties": []
                }

    # 5. Check if title matches target roles or is entry-friendly
    target_titles = [t.lower() for t in config.get("target_titles", [])]
    has_role_match = any(target in title for target in target_titles)
    if not has_role_match:
        flags.append("non_exact_title_match")
        uncertainties.append(f"Title '{title}' does not directly match target titles list")

    if is_remote and not is_india_local and not any(w in location for w in ["worldwide", "global"]):
        uncertainties.append("Remote job location should be checked for country-specific payroll restrictions")

    return {
        "eligible": True,
        "reason": "Passed screening guardrail; eligible for AI review and ranking",
        "flags": flags,
        "uncertainties": uncertainties
    }
