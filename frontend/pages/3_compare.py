"""Compare page - player comparison."""

import os
import streamlit as st
import plotly.graph_objects as go
import requests

import sys
sys.path.append('..')
from utils.theme import get_theme_css, render_header, theme_toggle, init_theme, apply_plotly_theme, get_chart_colors

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


def clean_team_name(team: str | None) -> str:
    """Clean team name - remove duplicate player name if present."""
    if not team:
        return "N/A"
    # If team contains " - ", take only the part after it
    if " - " in team:
        return team.split(" - ", 1)[1]
    return team


st.set_page_config(page_title="Compare", page_icon="⚖️", layout="wide")

# Theme setup
dark_mode = init_theme()
dark_mode = theme_toggle()
st.markdown(get_theme_css(dark_mode), unsafe_allow_html=True)

# Render header
render_header("Player Comparison", "⚖️")


def fetch_players(name=None, limit=100):
    """Fetch players from API."""
    try:
        if name:
            response = requests.get(f"{API_BASE_URL}/players/search", params={"name": name, "limit": limit})
        else:
            response = requests.get(f"{API_BASE_URL}/players/", params={"limit": limit})
        response.raise_for_status()
        return response.json()
    except:
        return []


def fetch_detailed_stats(player_id, season):
    """Fetch player detailed stats."""
    try:
        response = requests.get(f"{API_BASE_URL}/players/{player_id}/detailed-stats", params={"season": season})
        response.raise_for_status()
        return response.json()
    except:
        return None


# Fetch all players
all_players = fetch_players(limit=100)

if not all_players:
    st.error("⚠️ Backend not running! Start: `cd backend && uv run uvicorn app.main:app --reload --port 8000`")
    st.stop()

# Create options list with position display
player_options = {}
for p in all_players:
    team = clean_team_name(p.get("team"))
    pos_display = get_position_display(p.get("position"))
    label = f"{p['name']} - {team} ({pos_display})"
    player_options[label] = p

option_list = ["-- Select --"] + list(player_options.keys())

col1, col2 = st.columns(2)

with col1:
    sel1 = st.selectbox("Player 1", option_list, key="cmp_p1")

with col2:
    sel2 = st.selectbox("Player 2", option_list, key="cmp_p2")

# Season hardcoded to current
season_cmp = "2025/26"

# Check if players are selected
if sel1 != "-- Select --" and sel2 != "-- Select --":
    p1 = player_options[sel1]
    p2 = player_options[sel2]

    # Check if same player
    if p1['id'] == p2['id']:
        st.error("❌ Cannot compare a player with themselves. Select two different players.")
    elif p1.get("position") != p2.get("position") and (p1.get("position") == "GK" or p2.get("position") == "GK"):
        gk1 = p1.get("position") == "GK"
        gk2 = p2.get("position") == "GK"
        st.error("❌ Cannot compare goalkeeper with field player")
    else:
        gk1 = p1.get("position") == "GK"
        gk2 = p2.get("position") == "GK"
        is_gk = gk1
        is_gk = gk1
        st.info(f"📅 {season_cmp} | {'🧤 Goalkeepers' if is_gk else '⚽ Field Players'} | 📊 League games only")

        # Stats
        st.subheader("Select stats")
        stats = []

        if is_gk:
            x1, x2, x3 = st.columns(3)
            with x1:
                c1 = st.checkbox("Saves", True)
                c2 = st.checkbox("Save %", True)
                c3 = st.checkbox("Clean Sheets", True)
            with x2:
                c4 = st.checkbox("Goals Against", True)
                c5 = st.checkbox("Penalties Saved", True)
            with x3:
                c6 = st.checkbox("Matches", True)
                c7 = st.checkbox("Minutes", True)

            if c1: stats.append(("Saves", "saves"))
            if c2: stats.append(("Save %", "save_percentage"))
            if c3: stats.append(("Clean Sheets", "clean_sheets"))
            if c4: stats.append(("Goals Against", "goals_against"))
            if c5: stats.append(("Penalties Saved", "penalties_saved"))
            if c6: stats.append(("Matches", "matches_total"))
            if c7: stats.append(("Minutes", "minutes_played"))
        else:
            x1, x2 = st.columns(2)
            with x1:
                c1 = st.checkbox("Goals", True)
                c2 = st.checkbox("Assists", True)
                c3 = st.checkbox("G/90", True)
                c4 = st.checkbox("A/90", True)
            with x2:
                c5 = st.checkbox("Matches", True)
                c6 = st.checkbox("Minutes", False)

            if c1: stats.append(("Goals", "goals"))
            if c2: stats.append(("Assists", "assists"))
            if c3: stats.append(("G/90", "g_per90"))
            if c4: stats.append(("A/90", "a_per90"))
            if c5: stats.append(("Matches", "matches_total"))
            if c6: stats.append(("Minutes", "minutes_played"))

        if st.button("📊 Compare", type="primary"):
            if not stats:
                st.warning("Select stats")
            else:
                with st.spinner("Loading..."):
                    s1 = fetch_detailed_stats(p1["id"], season_cmp)
                    s2 = fetch_detailed_stats(p2["id"], season_cmp)

                if s1 and s2:
                    t1 = s1.get("league_stats") or s1.get("total", {})
                    t2 = s2.get("league_stats") or s2.get("total", {})

                    labels = [x[0] for x in stats]
                    keys = [x[1] for x in stats]
                    v1 = [float(t1.get(k, 0) or 0) for k in keys]
                    v2 = [float(t2.get(k, 0) or 0) for k in keys]

                    st.markdown(f"### {p1['name']} vs {p2['name']}")

                    # Radar - normalization
                    n1, n2 = [], []
                    for i, (a, b) in enumerate(zip(v1, v2)):
                        mx = max(a, b) if max(a, b) > 0 else 1
                        if keys[i] in ["goals_against", "yellow_cards", "red_cards"]:
                            n1.append(float((1 - a/mx) * 100))
                            n2.append(float((1 - b/mx) * 100))
                        else:
                            n1.append(float((a/mx) * 100))
                            n2.append(float((b/mx) * 100))

                    # Get colors
                    color1, color2 = get_chart_colors()

                    fig = go.Figure()
                    fig.add_trace(go.Scatterpolar(
                        r=n1 + [n1[0]],
                        theta=labels + [labels[0]],
                        fill='toself',
                        name=p1['name'],
                        line_color=color1
                    ))
                    fig.add_trace(go.Scatterpolar(
                        r=n2 + [n2[0]],
                        theta=labels + [labels[0]],
                        fill='toself',
                        name=p2['name'],
                        line_color=color2
                    ))
                    fig.update_layout(
                        polar=dict(radialaxis=dict(visible=True, range=[0, 100])),
                        height=400
                    )
                    fig = apply_plotly_theme(fig, dark_mode)
                    st.plotly_chart(fig, use_container_width=True)

                    # Bar
                    fig2 = go.Figure([
                        go.Bar(name=p1['name'], x=labels, y=v1, marker_color=color1),
                        go.Bar(name=p2['name'], x=labels, y=v2, marker_color=color2)
                    ])
                    fig2.update_layout(barmode='group', height=300)
                    fig2 = apply_plotly_theme(fig2, dark_mode)
                    st.plotly_chart(fig2, use_container_width=True)

                    # Table
                    st.dataframe({"Stat": labels, p1['name']: v1, p2['name']: v2}, hide_index=True)
                else:
                    st.warning("No data")
else:
    st.info("👆 Select two players from the lists above")
