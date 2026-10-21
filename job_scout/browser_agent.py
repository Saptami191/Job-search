import os
import re
import json
import asyncio
from typing import Dict, Any, Optional
import urllib.request
import urllib.parse
from .config import load_config

INSPECTION_PROMPT = """
Inspect the currently provided job listing page. Extract:
- Job title and company
- Location and remote-work restrictions
- Required skills
- Experience requirements
- Salary, if explicitly stated
- Application URL

CRITICAL SAFETY DIRECTIVE:
Do not click Apply, submit forms, or answer employer screening questions.
Return a concise structured JSON summary with the following keys:
{
  "title": string,
  "company": string,
  "location": string,
  "remote_work_restrictions": string,
  "required_skills": [string],
  "experience_requirements": string,
  "salary": string,
  "application_url": string,
  "uncertain_or_missing_info": [string]
}
"""

async def inspect_with_browser_use(url: str, model_name: str = "gpt-4o") -> Optional[Dict[str, Any]]:
    """
    Inspects a job listing page using browser-use and an LLM agent.
    Strictly read-only inspection. Never clicks Apply or submits forms.
    """
    try:
        from browser_use import Agent
        from langchain_openai import ChatOpenAI
    except ImportError:
        return None

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None

    task_desc = f"""
Navigate to {url}.
{INSPECTION_PROMPT}
"""
    try:
        llm = ChatOpenAI(model=model_name, temperature=0.0)
        agent = Agent(task=task_desc, llm=llm)
        result = await agent.run()
        # Parse output if structured JSON is returned
        raw_text = str(result)
        match = re.search(r"\{.*\}", raw_text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        return {
            "raw_agent_result": raw_text,
            "url": url,
            "method": "browser_use"
        }
    except Exception as e:
        print(f"[Warning] browser-use inspection failed ({e}), using fallback parser.")
        return None

def inspect_with_http_fallback(url: str) -> Dict[str, Any]:
    """
    Fast, reliable HTTP inspection fallback when browser-use or Chrome is not ready.
    Extracts text from public permitted listing and summarizes key fields.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    extracted_text = ""
    title_found = ""
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
            # Basic tag stripping
            title_match = re.search(r"<title>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
            if title_match:
                title_found = title_match.group(1).strip()
            # Remove scripts, styles
            clean_html = re.sub(r"<(script|style).*?>.*?</\1>", "", html, flags=re.IGNORECASE | re.DOTALL)
            clean_text = re.sub(r"<[^>]+>", " ", clean_html)
            clean_text = re.sub(r"\s+", " ", clean_text).strip()
            extracted_text = clean_text[:4000]
    except Exception as e:
        return {
            "url": url,
            "error": f"Failed to fetch job page: {e}",
            "method": "http_fallback"
        }

    # Attempt LLM extraction on fetched text if key is available
    openai_key = os.getenv("OPENAI_API_KEY")
    if openai_key:
        try:
            from langchain_openai import ChatOpenAI
            from langchain_core.messages import SystemMessage, HumanMessage
            llm = ChatOpenAI(model="gpt-4o", temperature=0.0)
            resp = llm.invoke([
                SystemMessage(content=INSPECTION_PROMPT),
                HumanMessage(content=f"Page text from URL {url}:\n\n{extracted_text}")
            ])
            text = resp.content.strip()
            if text.startswith("```"):
                text = re.sub(r"^```(?:json)?\s*", "", text)
                text = re.sub(r"\s*```$", "", text)
            data = json.loads(text)
            data["method"] = "http_llm_extraction"
            return data
        except Exception:
            pass

    # Heuristic text analysis
    return {
        "title": title_found or "Listing",
        "company": "See URL",
        "location": "See description",
        "remote_work_restrictions": "Check listing page",
        "required_skills": [],
        "experience_requirements": "Unspecified in fallback preview",
        "salary": "Not detected",
        "application_url": url,
        "uncertain_or_missing_info": [
            "Full details require direct review on official website",
            "Screening questions must be answered manually"
        ],
        "extracted_preview": extracted_text[:500],
        "method": "heuristic_fallback"
    }

async def inspect_job_url(url: str) -> Dict[str, Any]:
    """
    Main entry point for inspecting a job page.
    Attempts browser-use first, falls back gracefully.
    """
    config = load_config()
    model_name = config.get("llm_model", "gpt-4o")
    result = await inspect_with_browser_use(url, model_name)
    if result:
        return result
    return inspect_with_http_fallback(url)

def run_inspection(url: str) -> Dict[str, Any]:
    return asyncio.run(inspect_job_url(url))
