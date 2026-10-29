import json
import os
from datetime import date

import pandas as pd
import streamlit as st

import engine

st.set_page_config(page_title="Biz Idea Engine", page_icon="💡", layout="wide")
st.title("💡 Biz Idea Engine")
st.caption("Research the world → generate ideas → score for 'build & sell' → validate. AI + live web search.")

# ---------- Sidebar: settings & profile ----------
with st.sidebar:
    st.header("Settings")
    api_key = st.text_input(
        "Anthropic API key",
        type="password",
        value=os.getenv("ANTHROPIC_API_KEY", ""),
        help="Get one at console.anthropic.com. Stored only in this session.",
    )
    model = st.text_input("Model", value=engine.DEFAULT_MODEL)
    n_ideas = st.slider("Number of ideas", 4, 12, 8)

    st.header("Your profile")
    skills = st.text_area("Skills / background", placeholder="e.g. 5 yrs marketing, basic Python, sales")
    interests = st.text_input("Interests / industries", placeholder="e.g. health, education, logistics")
    regions = st.text_input("Regions to scan", value="Global (incl. India, SE Asia, Africa, LatAm, Europe, US)")
    budget = st.number_input("Starting budget (USD)", 0, 1_000_000, 2000, step=500)
    hours = st.number_input("Hours per week", 1, 80, 15)
    model_pref = st.selectbox(
        "Business type",
        ["Any", "SaaS / software", "AI-powered service", "Content / newsletter / community",
         "E-commerce / DTC", "Productized service / agency", "Marketplace / lead-gen"],
    )
    exit_years = st.slider("Target exit (years)", 1, 7, 3)

profile = dict(skills=skills, interests=interests, regions=regions, budget=budget,
               hours=hours, model=model_pref, exit_years=exit_years)

for key in ("trends", "ideas", "plans"):
    st.session_state.setdefault(key, {} if key == "plans" else None)

def need_key():
    if not api_key:
        st.error("Add your Anthropic API key in the sidebar.")
        st.stop()

# ---------- Tabs ----------
tab1, tab2, tab3, tab4 = st.tabs(["1 · Research", "2 · Ideas", "3 · Deep dive", "4 · Export"])

with tab1:
    st.subheader("Scan the internet for what's working now")
    if st.button("🌍 Run global research", type="primary"):
        need_key()
        with st.spinner("Searching the web (30-90 seconds)..."):
            try:
                st.session_state.trends = engine.scan_trends(profile, api_key, model)
            except Exception as e:
                st.error(f"Research failed: {e}")
    if st.session_state.trends:
        st.markdown(st.session_state.trends)

with tab2:
    st.subheader("Scored business ideas")
    st.caption("Score (0-100) weights: " + ", ".join(f"{k.replace('_', ' ')} {v}" for k, v in engine.WEIGHTS.items()))
    if st.button("✨ Generate ideas from research"):
        need_key()
        if not st.session_state.trends:
            st.warning("Run the research step first.")
        else:
            with st.spinner("Generating and scoring ideas..."):
                try:
                    st.session_state.ideas = engine.generate_ideas(
                        profile, st.session_state.trends, n_ideas, api_key, model)
                except Exception as e:
                    st.error(f"Idea generation failed: {e}")

    ideas = st.session_state.ideas
    if ideas:
        df = pd.DataFrame([{
            "Idea": i["name"], "Score": i["total_score"], "Cost $": i.get("startup_cost_usd"),
            "Months to revenue": i.get("months_to_first_revenue"),
            "Inspiration": i.get("country_inspiration"),
        } for i in ideas])
        st.dataframe(df, use_container_width=True, hide_index=True)

        for i in ideas:
            with st.expander(f"{i['total_score']} · {i['name']} — {i.get('one_liner', '')}"):
                c1, c2 = st.columns(2)
                c1.markdown(f"**Customer:** {i.get('target_customer')}")
                c1.markdown(f"**Problem:** {i.get('problem')}")
                c1.markdown(f"**Solution:** {i.get('solution')}")
                c1.markdown(f"**Revenue model:** {i.get('revenue_model')}")
                c2.markdown(f"**Proof of demand:** {i.get('example_proof')}")
                c2.markdown(f"**Exit multiple:** {i.get('realistic_exit_multiple')}")
                c2.markdown("**Likely acquirers:** " + ", ".join(i.get("likely_acquirers", [])))
                c2.markdown("**Risks:** " + "; ".join(i.get("main_risks", [])))
                st.info(f"**7-day test:** {i.get('first_7_day_test')}")
                st.bar_chart(pd.Series(i.get("scores", {})))

with tab3:
    st.subheader("Validate and plan one idea")
    ideas = st.session_state.ideas
    if not ideas:
        st.info("Generate ideas first.")
    else:
        choice = st.selectbox("Pick an idea", [i["name"] for i in ideas])
        if st.button("🔎 Deep dive (competitors, MVP, path to $1M, exit)"):
            need_key()
            idea = next(i for i in ideas if i["name"] == choice)
            with st.spinner("Researching competitors and building the plan..."):
                try:
                    st.session_state.plans[choice] = engine.deep_dive(idea, profile, api_key, model)
                except Exception as e:
                    st.error(f"Deep dive failed: {e}")
        if choice in st.session_state.plans:
            st.markdown(st.session_state.plans[choice])

with tab4:
    st.subheader("Export")
    if st.session_state.ideas:
        st.download_button("⬇️ Ideas (JSON)", json.dumps(st.session_state.ideas, indent=2),
                           f"ideas_{date.today()}.json", "application/json")
    if st.session_state.trends:
        st.download_button("⬇️ Research (Markdown)", st.session_state.trends,
                           f"research_{date.today()}.md")
    for name, plan in st.session_state.plans.items():
        st.download_button(f"⬇️ Plan: {name}", plan, f"plan_{name[:30].replace(' ', '_')}.md", key=name)
