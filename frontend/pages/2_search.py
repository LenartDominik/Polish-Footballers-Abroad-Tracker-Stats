"""Search page - advanced player search."""

import os

import streamlit as st
import requests

import sys
sys.path.append('..')
from utils.theme import get_theme_css, render_header
from translations import t, language_selector, get_position_display, clean_team_name

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000/api/v1")

language_selector()

st.set_page_config(page_title="Search", page_icon="🔍", layout="wide")

# Apply theme CSS
st.markdown(get_theme_css(), unsafe_allow_html=True)

# Render header
render_header(t("player_search").lstrip("🔍 "), "🔍")

# Search form
col1, col2 = st.columns([2, 2])
with col1:
    name = st.text_input(t("name"), placeholder=t("name_placeholder"))
with col2:
    team = st.text_input(t("club").lstrip("🏟️ "), placeholder=t("club_placeholder"))

limit = st.slider(t("max_results"), 5, 100, 20)

if st.button(t("search_btn"), type="primary"):
    if not any([name, team]):
        st.warning(t("enter_criteria"))
    else:
        with st.spinner(t("searching")):
            try:
                params = {"limit": limit}
                if name:
                    params["name"] = name
                if team:
                    params["team"] = team

                response = requests.get(f"{API_BASE_URL}/players/search", params=params)
                response.raise_for_status()
                players = response.json()

                if players:
                    st.success(t("found_players", count=len(players)))

                    for p in players:
                        pos_display = get_position_display(p.get("position"))
                        team_name = clean_team_name(p.get("team"))

                        st.markdown(f"""
                        <div class="player-card">
                            <div class="player-name">{p['name']}</div>
                            <div class="player-info">{team_name} | {pos_display}</div>
                        </div>
                        """, unsafe_allow_html=True)
                else:
                    st.info(t("no_players_criteria"))

            except requests.RequestException as e:
                st.error(t("api_error", error=e))
