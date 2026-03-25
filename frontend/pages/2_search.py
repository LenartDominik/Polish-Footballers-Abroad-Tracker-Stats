"""Search page - advanced player search."""

import os

import streamlit as st
import pandas as pd
import requests

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000/api/v1")


def get_position_display(position: str | None) -> str:
    """Return position with emoji."""
    if position == "GK":
        return "🧤 Goalkeeper"
    elif position in ["F", "FW", "Forward", "ST", "CF"]:
        return "⚽ Forward"
    elif position in ["M", "MF", "Midfielder"]:
        return "⚽ Midfielder"
    elif position in ["D", "DF", "Defender"]:
        return "⚽ Defender"
    elif position:
        return f"⚽ {position}"
    else:
        return "⚽ Unknown"


st.set_page_config(page_title="Search", page_icon="🔍", layout="wide")

st.markdown("""
<div style="text-align: center;">
    <h1>🇵🇱 Polish Footballers Abroad</h1>
    <p style="font-size: 1.2rem; color: #888;">Track Polish footballers in the best leagues worldwide!</p>
</div>
""", unsafe_allow_html=True)
st.markdown("---")
st.subheader("🔍 Player Search")

# Search form
col1, col2, col3 = st.columns([2, 2, 2])
with col1:
    name = st.text_input("Name", placeholder="e.g. Lewandowski, Szczesny...")
with col2:
    team = st.text_input("Club", placeholder="e.g. Barcelona, Juventus...")
with col3:
    league = st.text_input("League", placeholder="e.g. La Liga, Serie A...")

limit = st.slider("Max results", 5, 100, 20)

if st.button("🔍 Search", type="primary"):
    if not any([name, team, league]):
        st.warning("Enter at least one search criteria")
    else:
        with st.spinner("Searching..."):
            try:
                params = {"limit": limit}
                if name:
                    params["name"] = name
                if team:
                    params["team"] = team
                if league:
                    params["league"] = league

                response = requests.get(f"{API_BASE_URL}/players/search", params=params)
                response.raise_for_status()
                players = response.json()

                if players:
                    st.success(f"Found {len(players)} players")

                    # Display with position
                    for p in players:
                        pos_display = get_position_display(p.get("position"))
                        st.markdown(f"**{p['name']}** - {p.get('team', 'N/A')} ({pos_display})")
                else:
                    st.info("No players found matching criteria")

            except requests.RequestException as e:
                st.error(f"API connection error: {e}")
