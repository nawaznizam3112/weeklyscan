"""Core engine: web research + idea generation + exit-focused scoring."""
import json
import os
import re

from anthropic import Anthropic

DEFAULT_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-5-5")
SEARCH_TOOL = {"type": "web_search_20250305", "name": "web_search", "max_uses": 6}

# Weights for the "build it and sell it" score (sum = 100)
WEIGHTS = {
    "exit_appeal": 25,      # recurring revenue, acquirers exist, clean to hand over
    "margin": 20,           # gross/net margin potential
    "scalability": 15,      # grows without growing headcount 1:1
    "easy_start": 15,       # low capital / fast to first revenue
    "competition_gap": 15,  # underserved niche or weak incumbents
    "founder_fit": 10,      # matches the person's skills/resources
}


def _client(api_key=None):
    return Anthropic(api_key=api_key or os.getenv("ANTHROPIC_API_KEY"))


def _ask(system, user, api_key=None, model=DEFAULT_MODEL, search=True, max_tokens=4000):
    """Call Claude (optionally with live web search) and return the text."""
    client = _client(api_key)
    messages = [{"role": "user", "content": user}]
    kwargs = {"model": model, "max_tokens": max_tokens, "system": system}
    if search:
        kwargs["tools"] = [SEARCH_TOOL]

    for _ in range(6):  # handle long search turns that get paused
        resp = client.messages.create(messages=messages, **kwargs)
        if resp.stop_reason == "pause_turn":
            messages = [messages[0], {"role": "assistant", "content": resp.content}]
            continue
        break
    return "".join(b.text for b in resp.content if b.type == "text").strip()


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
        "You are a business researcher. Use web search to find REAL, current evidence. "
        "Prefer sources like acquisition marketplaces (Acquire.com, Flippa, Empire Flippers), "
        "Indie Hackers, Product Hunt, Y Combinator, Crunchbase, news, and industry reports. "
        "Cite source names/URLs inline. Never invent numbers."
    )
    user = f"""Research what is working RIGHT NOW (today's date matters) for someone with this profile:

{profile_text(profile)}

Find and summarize:
1. 6-8 fast-growing niches/trends globally (include emerging markets like India, SE Asia, Africa, LatAm, not just US).
2. What types of small businesses are actually being SOLD on acquisition marketplaces and at what typical revenue multiples.
3. Problems/pain points people are complaining about that software, services or AI could solve.
4. Business models that are proven in one country but not yet copied in others (geographic arbitrage).

Return concise markdown with sources."""
    return _ask(system, user, api_key, model, search=True, max_tokens=5000)


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
    raw = _ask(system, user, api_key, model, search=False, max_tokens=7000)
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
        "You are a pragmatic startup advisor. Use web search to check real competitors, "
        "pricing and demand. Be honest about weaknesses. Cite sources."
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
    return _ask(system, user, api_key, model, search=True, max_tokens=6000)
