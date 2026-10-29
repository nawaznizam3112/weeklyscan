"""Headless run for GitHub Actions: writes a dated report into /reports."""
import json
import os
from datetime import date

import engine

profile = dict(
    skills=os.getenv("PROFILE_SKILLS", ""),
    interests=os.getenv("PROFILE_INTERESTS", ""),
    regions=os.getenv("PROFILE_REGIONS", "Global"),
    budget=os.getenv("PROFILE_BUDGET", "2000"),
    hours=os.getenv("PROFILE_HOURS", "15"),
    model="Any",
    exit_years=3,
)

trends = engine.scan_trends(profile)
ideas = engine.generate_ideas(profile, trends, n=8)

os.makedirs("reports", exist_ok=True)
path = f"reports/{date.today()}.md"
with open(path, "w", encoding="utf-8") as f:
    f.write(f"# Business idea scan — {date.today()}\n\n## Research\n\n{trends}\n\n## Ranked ideas\n\n")
    for i in ideas:
        f.write(f"### {i['total_score']} · {i['name']}\n{i.get('one_liner', '')}\n\n"
                f"- Customer: {i.get('target_customer')}\n- Revenue: {i.get('revenue_model')}\n"
                f"- Exit: {i.get('realistic_exit_multiple')}\n- 7-day test: {i.get('first_7_day_test')}\n\n")
with open(path.replace(".md", ".json"), "w", encoding="utf-8") as f:
    json.dump(ideas, f, indent=2)
print("Wrote", path)
