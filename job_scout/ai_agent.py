import json
import os
import re
from typing import Dict, Any, List, Tuple
from .config import load_config, load_candidate_profile

def screen_job_heuristic(job: Dict[str, Any], config: Dict[str, Any], profile: Dict[str, Any]) -> Dict[str, Any]:
    """
    Fallback deterministic evaluation engine used when no LLM key is configured.
    Evaluates required skills, preferred skills, early-career fit, and flags.
    """
    title = str(job.get("title") or "").lower()
    desc = str(job.get("description") or "").lower()
    full_text = f"{title} {desc}"

    req_skills = [s.strip() for s in config.get("required_skills", [])]
    pref_skills = [s.strip() for s in config.get("preferred_skills", [])]

    matched_req = []
    missing_req = []
    for s in req_skills:
        pattern = r"(?<![a-z0-9+#.])" + re.escape(s.lower()) + r"(?![a-z0-9+#.])"
        if re.search(pattern, full_text):
            matched_req.append(s)
        else:
            missing_req.append(s)

    matched_pref = []
    for s in pref_skills:
        pattern = r"(?<![a-z0-9+#.])" + re.escape(s.lower()) + r"(?![a-z0-9+#.])"
        if re.search(pattern, full_text):
            matched_pref.append(s)

    # Calculate weighted score (Required skills 70%, Preferred 30%)
    req_ratio = len(matched_req) / max(1, len(req_skills))
    pref_ratio = len(matched_pref) / max(1, len(pref_skills))
    raw_score = int(round((req_ratio * 70) + (pref_ratio * 30)))

    # Bonus for direct target title match
    target_titles = [t.lower() for t in config.get("target_titles", [])]
    if any(t in title for t in target_titles):
        raw_score = min(100, raw_score + 10)

    # Determine verdict
    if raw_score >= 60:
        verdict = "STRONGLY_RECOMMENDED"
    elif raw_score >= 35:
        verdict = "RECOMMENDED"
    elif raw_score >= 20:
        verdict = "BORDERLINE"
    else:
        verdict = "NOT_RECOMMENDED"

    pros = []
    if matched_req:
        pros.append(f"Matches core skills: {', '.join(matched_req[:4])}")
    if matched_pref:
        pros.append(f"Matches preferred stack: {', '.join(matched_pref[:3])}")
    if any(term in title for term in ["backend", "platform", "infrastructure"]):
        pros.append("High alignment with primary target engineering domain")

    cons = []
    if missing_req and len(missing_req) > len(matched_req):
        cons.append(f"Missing mentions of: {', '.join(missing_req[:3])}")
    if not job.get("salary"):
        cons.append("Salary not explicitly stated in listing")

    uncertainties = []
    if not job.get("location") or "remote" not in str(job.get("location")).lower() and "india" not in str(job.get("location")).lower():
        uncertainties.append("Confirm location and tax residency eligibility")

    return {
        "score": raw_score,
        "verdict": verdict,
        "summary": f"Job aligns with {len(matched_req)}/{len(req_skills)} required skills and {len(matched_pref)} preferred skills.",
        "matched_required_skills": matched_req,
        "matched_preferred_skills": matched_pref,
        "pros": pros,
        "cons": cons,
        "uncertainties": uncertainties,
        "method": "heuristic_analyzer"
    }

def screen_job_with_llm(job: Dict[str, Any], config: Dict[str, Any], profile: Dict[str, Any]) -> Dict[str, Any]:
    """
    Deep semantic evaluation using an LLM.
    Supports OpenAI, Gemini, or LangChain.
    """
    openai_key = os.getenv("OPENAI_API_KEY")
    gemini_key = os.getenv("GEMINI_API_KEY")

    if not openai_key and not gemini_key:
        return screen_job_heuristic(job, config, profile)

    prompt = f"""
You are an expert technical recruiter evaluating a job listing for an early-career candidate.

CANDIDATE PROFILE:
- Target roles: {json.dumps(config.get('target_titles'))}
- Required skills: {json.dumps(config.get('required_skills'))}
- Preferred skills: {json.dumps(config.get('preferred_skills'))}
- Candidate location and remote preferences are provided by the configuration.
- Experience limit: Max 2 years (Entry-level / SDE 1)

JOB LISTING TO EVALUATE:
- Title: {job.get('title')}
- Company: {job.get('company')}
- Location: {job.get('location')}
- Experience requirement: {job.get('experience')}
- Description: {job.get('description', '')[:2500]}

EVALUATION RULES:
1. Don't reject strong entry-level roles just because they don't mention every technology.
2. Flag any uncertain requirements (visa sponsorship ambiguity, hidden senior requirements, night shifts).
3. Score from 0 to 100 based on realistic technical fit for early-career backend/infra.
4. Output STRICT JSON only with keys:
   "score": int (0-100),
   "verdict": "STRONGLY_RECOMMENDED" | "RECOMMENDED" | "BORDERLINE" | "NOT_RECOMMENDED",
   "summary": string (2-3 sentences),
   "matched_required_skills": list of strings,
   "matched_preferred_skills": list of strings,
   "pros": list of strings,
   "cons": list of strings,
   "uncertainties": list of strings
"""

    # Attempt OpenAI first if configured
    if openai_key:
        try:
            from langchain_openai import ChatOpenAI
            from langchain_core.messages import SystemMessage, HumanMessage

            model_name = config.get("llm_model", "gpt-4o")
            llm = ChatOpenAI(model=model_name, temperature=0.1)
            resp = llm.invoke([
                SystemMessage(content="You evaluate job listings objectively. Respond ONLY with valid JSON."),
                HumanMessage(content=prompt)
            ])
            text = resp.content.strip()
            # Clean markdown codeblocks if present
            if text.startswith("```"):
                text = re.sub(r"^```(?:json)?\s*", "", text)
                text = re.sub(r"\s*```$", "", text)
            result = json.loads(text)
            result["method"] = f"llm_{model_name}"
            return result
        except Exception as e:
            print(f"[Warning] LLM evaluation failed ({e}), falling back to heuristic.")
            return screen_job_heuristic(job, config, profile)

    return screen_job_heuristic(job, config, profile)

def evaluate_job_match(job: Dict[str, Any]) -> Dict[str, Any]:
    config = load_config()
    profile = load_candidate_profile()
    return screen_job_with_llm(job, config, profile)
