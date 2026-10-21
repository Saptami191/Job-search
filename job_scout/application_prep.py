import re
from pathlib import Path
from typing import Any, Dict, List

from .config import APPLICATIONS_DIR, load_candidate_profile, load_config


def prepare_application_dossier(
    job: Dict[str, Any], ai_analysis: Dict[str, Any] | None = None
) -> Path:
    config = load_config()
    profile = load_candidate_profile()
    job_id = str(job.get("job_id") or "job").strip()
    safe_folder = re.sub(r"[^a-zA-Z0-9_-]", "_", job_id)[:50]
    dest_dir = APPLICATIONS_DIR / safe_folder
    dest_dir.mkdir(parents=True, exist_ok=True)

    title = job.get("title", "Software Engineer")
    company = job.get("company", "Company")
    matched_skills: List[str] = []
    if ai_analysis:
        matched_skills.extend(ai_analysis.get("matched_required_skills", []))
        matched_skills.extend(ai_analysis.get("matched_preferred_skills", []))
    if not matched_skills and job.get("matched_skills"):
        matched_skills = [
            skill.strip()
            for skill in str(job["matched_skills"]).split(",")
            if skill.strip()
        ]

    resume_md = dest_dir / "tailored_resume.md"
    generate_tailored_resume_md(
        resume_md,
        profile,
        title,
        company,
        matched_skills,
        job.get("description", ""),
    )
    generate_tailored_resume_tex(
        dest_dir / "tailored_resume.tex",
        profile,
        title,
        company,
        matched_skills,
    )
    answers = dest_dir / "screening_answers.md"
    generate_screening_answers(answers, profile, title, company, ai_analysis)
    generate_approval_checklist(
        dest_dir / "approval_checklist.md",
        job,
        ai_analysis or {},
        resume_md,
        answers,
    )
    return dest_dir


def _profile_value(profile: Dict[str, Any], key: str, default: str) -> str:
    return str(profile.get(key) or default)


def generate_tailored_resume_md(
    dest: Path,
    profile: Dict[str, Any],
    job_title: str,
    company: str,
    matched_skills: List[str],
    job_desc: str,
) -> None:
    name = _profile_value(profile, "name", "Your Name")
    email = _profile_value(profile, "email", "you@example.com")
    phone = _profile_value(profile, "phone", "+00 0000000000")
    location = _profile_value(profile, "location", "Your City, Country")
    links = [
        (label, profile.get(key))
        for label, key in (
            ("LinkedIn", "linkedin"),
            ("GitHub", "github"),
            ("LeetCode", "leetcode"),
            ("GeeksforGeeks", "geeksforgeeks"),
            ("Portfolio", "portfolio"),
        )
        if profile.get(key)
    ]
    link_text = " | ".join(f"[{label}]({url})" for label, url in links)
    skills = profile.get("skills", {})
    languages = ", ".join(skills.get("programming_languages", []))
    backend = ", ".join(skills.get("backend_data_layer", []))
    tooling = ", ".join(skills.get("tooling_infrastructure", []))

    lines = [
        f"# {name}",
        f"**{location}** | {phone} | [{email}](mailto:{email})",
        link_text,
        "",
        "> **Human approval gate**: Review every fact before submitting.",
        f"> **Application target**: {job_title} at **{company}**.",
        "",
        "## Professional Summary",
        (
            f"Early-career engineer with experience and projects supplied in the "
            f"candidate profile. Relevant skills for this role: "
            f"{', '.join(matched_skills[:4]) or 'see technical skills below'}."
        ),
        "",
        "## Education",
    ]
    for education in profile.get("education", []):
        lines.append(
            f"- **{education.get('institution', 'Institution')}** — "
            f"{education.get('degree', 'Degree')} "
            f"({education.get('duration', education.get('graduation_year', ''))})"
        )

    lines.extend(
        [
            "",
            "## Technical Skills",
            f"- **Languages**: {languages or 'Not provided'}",
            f"- **Backend & Data Layer**: {backend or 'Not provided'}",
            f"- **Tooling & Infrastructure**: {tooling or 'Not provided'}",
        ]
    )
    if matched_skills:
        lines.append(f"- **Role matches**: {', '.join(matched_skills)}")

    for heading, entries in (
        ("Open Source Contributions", profile.get("open_source_contributions", [])),
        ("Selected Projects", profile.get("projects", [])),
    ):
        if not entries:
            continue
        lines.extend(["", f"## {heading}"])
        for entry in entries:
            label = entry.get("name") or entry.get("role") or "Entry"
            details = entry.get("tech") or entry.get("organizations") or ""
            lines.append(f"### {label} {f'| *{details}*' if details else ''}")
            for highlight in entry.get("highlights", []):
                lines.append(f"- {highlight}")

    dest.write_text("\n".join(lines) + "\n", encoding="utf-8")


def generate_tailored_resume_tex(
    dest: Path,
    profile: Dict[str, Any],
    job_title: str,
    company: str,
    matched_skills: List[str],
) -> None:
    name = _profile_value(profile, "name", "Your Name")
    email = _profile_value(profile, "email", "you@example.com")
    phone = _profile_value(profile, "phone", "+00 0000000000")
    location = _profile_value(profile, "location", "Your City, Country")
    skills = ", ".join(matched_skills) or "See candidate profile"
    tex = rf"""\documentclass{{article}}
\usepackage[margin=0.7in]{{geometry}}
\usepackage{{hyperref}}
\begin{{document}}
\begin{{center}}
{{\Large\bfseries {name}}}\\
{location} \textbar\ {phone} \textbar\ \href{{mailto:{email}}}{{{email}}}\\
\textit{{Target: {job_title} at {company}}}
\end{{center}}
\section*{{Summary}}
This draft contains only facts supplied in the local candidate profile. Review it
before use. Relevant role matches: {skills}.
\section*{{Education}}
"""
    for education in profile.get("education", []):
        tex += (
            rf"\textbf{{{education.get('institution', 'Institution')}}} --- "
            rf"{education.get('degree', 'Degree')} "
            rf"({education.get('duration', education.get('graduation_year', ''))})\\"
            "\n"
        )
    tex += r"\end{document}" + "\n"
    dest.write_text(tex, encoding="utf-8")


def generate_screening_answers(
    dest: Path,
    profile: Dict[str, Any],
    job_title: str,
    company: str,
    ai_analysis: Dict[str, Any] | None = None,
) -> None:
    name = _profile_value(profile, "name", "Your Name")
    lines = [
        f"# Application Screening Q&A Draft: {job_title} at {company}",
        f"**Candidate**: {name}",
        "",
        "> Review all answers. The system does not submit applications automatically.",
        "",
        "## Verified factual answers",
    ]
    for question, answer in profile.get("verified_screening_answers", {}).items():
        lines.extend([f"**Q: {question}**", f"- **Verified answer**: {answer}", ""])
    lines.extend(
        [
            "---",
            "## Questions requiring human input",
            "- Why do you want to join this company?",
            "- What are your salary or stipend expectations?",
            "- When can you start and what are your work preferences?",
            "",
            "Add truthful, role-specific responses before applying.",
        ]
    )
    if ai_analysis and ai_analysis.get("uncertainties"):
        lines.extend(["", "## Listing uncertainties to verify"])
        lines.extend(f"- {item}" for item in ai_analysis["uncertainties"])
    dest.write_text("\n".join(lines) + "\n", encoding="utf-8")


def generate_approval_checklist(
    dest: Path,
    job: Dict[str, Any],
    ai_analysis: Dict[str, Any],
    resume_path: Path,
    answers_path: Path,
) -> None:
    score = ai_analysis.get("score", job.get("score", 0))
    verdict = ai_analysis.get("verdict", "REVIEW")
    url = job.get("url", "")
    lines = [
        f"# Human Approval Gate: {job.get('title', '')} @ {job.get('company', '')}",
        "",
        f"- **Job ID**: `{job.get('job_id', '')}`",
        f"- **Location**: {job.get('location', '')}",
        f"- **Relevance score**: **{score}/100** ({verdict})",
        f"- **Official listing URL**: {url or 'Not provided'}",
        "",
        "## Review checklist",
        "- [ ] Verify the official listing and closing date.",
        "- [ ] Confirm location, eligibility, and experience requirements.",
        f"- [ ] Review `{resume_path.name}` and verify every fact.",
        f"- [ ] Review `{answers_path.name}` and complete human-input answers.",
        "- [ ] Submit manually through the official employer portal.",
        "- [ ] Update the application status after submission.",
    ]
    dest.write_text("\n".join(lines) + "\n", encoding="utf-8")
