"""Core engine: web research + idea generation + exit-focused scoring (Gemini)."""
import json
import os
import re

from google import genai
from google.genai import types

DEFAULT_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

# Weights for the "build it and sell it" score (sum = 100)
WEIGHTS = {
    "exit_appeal": 25,      # recurring revenue, acquirers exist, clean to hand over
    "margin": 20,           # gross/net margin potential
    "scalability": 15,      # grows without growing headcount 1:1
    "easy_start": 15,       # low capital / fast to first revenue
    "competition_gap": 15,  # underserved niche or weak incumbents
    "founder_fit": 10,      # matches the person's skills/resources
}


def _ask(system, user, api_key=None, model=DEFAULT_MODEL, search=True, json_out=False):
    """Call Gemini (optionally grounded with live Google Search) and return text."""
    client = genai.Client(api_key=api_key or os.getenv("GEMINI_API_KEY"))
    cfg = {"system_instruction": system, "temperature": 0.7}
    if search:
        cfg["tools"] = [types.Tool(google_search=types.GoogleSearch())]
    if json_out:  # JSON mode can't be combined with the search tool
        cfg["response_mime_type"] = "application/json"
    resp = client.models.generate_content(
        model=model, contents=user, config=types.GenerateContentConfig(**cfg)
    )
    text = (resp.text or "").strip()

    if search:  # append the real web sources Gemini used
        try:
            chunks = resp.candidates[0].grounding_metadata.grounding_chunks or []
            seen, lines = set(), []
            for c in chunks:
                if c.web and c.web.uri not in seen:
                    seen.add(c.web.uri)
                    lines.append(f"- [{c.web.title or c.web.uri}]({c.web.uri})")
            if lines:
                text += "\n\n**Sources searched:**\n" + "\n".join(lines)
        except Exception:
            pass
    return text


def _extract_json(text):
    text = re.sub(r"```(?:json)?", "", text).strip()
    start = min([i for i in (text.find("["), text.find("{")) if i != -1], default=-1)
    if start == -1:
        raise ValueError("No JSON found in model output")
    end = max(text.rfind("]"), text.rfind("}"))
    return json.loads(text[start:end + 1])


def profile_text(p):
    return (
        f"Skills/background: {p.get('skills') or 'not given'}\n"
        f"Starting budget (USD): {p.get('budget') or 'not given'}\n"
        f"Hours per week: {p.get('hours') or 'not given'}\n"
        f"Interests/industries: {p.get('interests') or 'open'}\n"
        f"Regions to scan: {p.get('regions') or 'global'}\n"
        f"Business type preference: {p.get('model') or 'any'}\n"
        f"Exit horizon: {p.get('exit_years') or 3} years"
    )


def scan_trends(profile, api_key=None, model=DEFAULT_MODEL):
    """Step 1: research what is actually working around the world right now."""
    system = (
        "You are a business researcher. Use Google Search to find REAL, current evidence. "
        "Prefer sources like acquisition marketplaces (Acquire.com, Flippa, Empire Flippers), "
        "Indie Hackers, Product Hunt, Y Combinator, Crunchbase, news, and industry reports. "
        "Name your sources inline. Never invent numbers."
    )
    user = f"""Research what is working RIGHT NOW for someone with this profile:

{profile_text(profile)}

Find and summarize:
1. 6-8 fast-growing niches/trends globally (include emerging markets like India, SE Asia, Africa, LatAm, not just US).
2. What types of small businesses are actually being SOLD on acquisition marketplaces and at what typical revenue multiples.
3. Problems/pain points people complain about that software, services or AI could solve.
4. Business models proven in one country but not yet copied in others (geographic arbitrage).

Return concise markdown."""
    return _ask(system, user, api_key, model, search=True)


def generate_ideas(profile, trends_md, n=8, api_key=None, model=DEFAULT_MODEL):
    """Step 2: turn research into scored business ideas (JSON)."""
    system = (
        "You are a startup analyst focused on businesses that can be built and SOLD. "
        "Be realistic and specific. Return ONLY valid JSON, no prose."
    )
    user = f"""Profile:
{profile_text(profile)}

Research:
{trends_md}

Generate {n} specific, differentiated business ideas (not vague categories) that fit this person
and could realistically be built then sold within the exit horizon. Mix countries/models.

Return a JSON array. Each item:
{{
  "name": str,
  "one_liner": str,
  "target_customer": str,
  "problem": str,
  "solution": str,
  "revenue_model": str,
  "example_proof": "real company/trend that shows demand (from research)",
  "country_inspiration": str,
  "startup_cost_usd": int,
  "months_to_first_revenue": int,
  "realistic_exit_multiple": "e.g. 3-4x annual profit, with reasoning",
  "likely_acquirers": [str],
  "main_risks": [str],
  "first_7_day_test": str,
  "scores": {{"exit_appeal":1-10,"margin":1-10,"scalability":1-10,"easy_start":1-10,"competition_gap":1-10,"founder_fit":1-10}}
}}"""
    raw = _ask(system, user, api_key, model, search=False, json_out=True)
    ideas = _extract_json(raw)
    for idea in ideas:
        idea["total_score"] = score(idea.get("scores", {}))
    return sorted(ideas, key=lambda i: i["total_score"], reverse=True)


def score(scores):
    """Weighted 0-100 score."""
    total = sum(WEIGHTS[k] * float(scores.get(k, 0)) / 10 for k in WEIGHTS)
    return round(total, 1)


def deep_dive(idea, profile, api_key=None, model=DEFAULT_MODEL):
    """Step 3: validation + execution plan for one chosen idea."""
    system = (
        "You are a pragmatic startup advisor. Use Google Search to check real competitors, "
        "pricing and demand. Be honest about weaknesses."
    )
    user = f"""Profile:
{profile_text(profile)}

Idea:
{json.dumps(idea, indent=2)}

Produce a markdown plan with these sections:
## Reality check (is demand real? top 5 real competitors + pricing)
## Ideal customer and where to find them
## MVP in 14 days (what to build/not build)
## 90-day launch plan (week by week)
## Path to $1M: revenue math (price x customers, channels, assumptions)
## Making it sellable (metrics buyers want, documentation, recurring revenue, owner-independence)
## Exit plan (marketplaces, brokers, likely buyers, realistic valuation range)
## Biggest risks and kill criteria (when to stop)"""
    return _ask(system, user, api_key, model, search=True)
