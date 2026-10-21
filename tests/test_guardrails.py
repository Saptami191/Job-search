from job_scout.guardrails import evaluate_job


CONFIG = {
    "candidate_location": "India",
    "require_india_eligibility": True,
    "experience_max_years": 2,
    "target_titles": ["Backend Engineer"],
    "avoid_keywords": ["Senior", "Unpaid"],
}


def test_accepts_india_entry_level_role():
    result = evaluate_job(
        {
            "title": "Backend Engineer",
            "description": "Build Python APIs.",
            "location": "Remote India",
            "eligible_countries": "India",
            "experience": "0-2 years",
        },
        CONFIG,
    )

    assert result["eligible"] is True


def test_rejects_unpaid_role():
    result = evaluate_job(
        {
            "title": "Unpaid Backend Intern",
            "description": "Work on APIs.",
            "location": "Remote",
            "eligible_countries": "Worldwide",
            "experience": "Internship",
        },
        CONFIG,
    )

    assert result["eligible"] is False
    assert "unpaid" in result["reason"].lower()


def test_rejects_foreign_only_role():
    result = evaluate_job(
        {
            "title": "Infrastructure Engineer",
            "description": "US citizenship required.",
            "location": "New York, NY",
            "eligible_countries": "US Only",
            "experience": "Entry-level",
        },
        CONFIG,
    )

    assert result["eligible"] is False
