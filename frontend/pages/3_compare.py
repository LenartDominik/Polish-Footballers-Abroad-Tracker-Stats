"""Compare page - player comparison."""

import os
import streamlit as st
import plotly.graph_objects as go
import requests

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000/api/v1")

st.set_page_config(page_title="Porównaj", page_icon="⚖️", layout="wide")

st.title("⚖️ Porównywarka Piłkarzy")


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


# Pobierz wszystkich graczy
all_players = fetch_players(limit=100)

if not all_players:
    st.error("⚠️ Backend nie działa! Uruchom: `cd backend && uv run uvicorn app.main:app --reload --port 8000`")
    st.stop()

# Stwórz listę opcji
player_options = {}
for p in all_players:
    pos = p.get("position", "?")
    team = p.get("team", "?")
    label = f"{p['name']} ({pos}) - {team}"
    player_options[label] = p

option_list = ["-- Wybierz --"] + list(player_options.keys())

col1, col2 = st.columns(2)

with col1:
    sel1 = st.selectbox("Piłkarz 1", option_list, key="cmp_p1")

with col2:
    sel2 = st.selectbox("Piłkarz 2", option_list, key="cmp_p2")

season_cmp = st.selectbox("Sezon", ["2025/26", "2024/25"], key="cmp_season")

# Sprawdź czy wybrano graczy
if sel1 != "-- Wybierz --" and sel2 != "-- Wybierz --":
    p1 = player_options[sel1]
    p2 = player_options[sel2]

    gk1 = p1.get("position") == "GK"
    gk2 = p2.get("position") == "GK"

    if gk1 != gk2:
        st.error("❌ Nie można porównać bramkarza z graczem z pola")
    else:
        is_gk = gk1
        st.info(f"📅 {season_cmp} | {'🧤 Bramkarze' if is_gk else '⚽ Gracze z pola'} | 📊 Tylko rozgrywki ligowe")

        # Stats
        st.subheader("Wybierz statystyki")
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
                c6 = st.checkbox("Mecze", True)
                c7 = st.checkbox("Minuty", True)

            if c1: stats.append(("Saves", "saves"))
            if c2: stats.append(("Save %", "save_percentage"))
            if c3: stats.append(("Clean Sheets", "clean_sheets"))
            if c4: stats.append(("Goals Against", "goals_against"))
            if c5: stats.append(("Penalties Saved", "penalties_saved"))
            if c6: stats.append(("Mecze", "matches_total"))
            if c7: stats.append(("Minuty", "minutes_played"))
        else:
            x1, x2 = st.columns(2)
            with x1:
                c1 = st.checkbox("Gole", True)
                c2 = st.checkbox("Asysty", True)
                c3 = st.checkbox("G/90", True)
                c4 = st.checkbox("A/90", True)
            with x2:
                c5 = st.checkbox("Mecze", True)
                c6 = st.checkbox("Minuty", False)

            if c1: stats.append(("Gole", "goals"))
            if c2: stats.append(("Asysty", "assists"))
            if c3: stats.append(("G/90", "g_per90"))
            if c4: stats.append(("A/90", "a_per90"))
            if c5: stats.append(("Mecze", "matches_total"))
            if c6: stats.append(("Minuty", "minutes_played"))

        if st.button("📊 Porównaj", type="primary"):
            if not stats:
                st.warning("Wybierz statystyki")
            else:
                with st.spinner("Ładuję..."):
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

                    # Radar - normalizacja
                    n1, n2 = [], []
                    for i, (a, b) in enumerate(zip(v1, v2)):
                        mx = max(a, b) if max(a, b) > 0 else 1
                        if keys[i] in ["goals_against", "yellow_cards", "red_cards"]:
                            n1.append(float((1 - a/mx) * 100))
                            n2.append(float((1 - b/mx) * 100))
                        else:
                            n1.append(float((a/mx) * 100))
                            n2.append(float((b/mx) * 100))

                    fig = go.Figure()
                    fig.add_trace(go.Scatterpolar(
                        r=n1 + [n1[0]],
                        theta=labels + [labels[0]],
                        fill='toself',
                        name=p1['name'],
                        line_color='#FF6B6B'
                    ))
                    fig.add_trace(go.Scatterpolar(
                        r=n2 + [n2[0]],
                        theta=labels + [labels[0]],
                        fill='toself',
                        name=p2['name'],
                        line_color='#4ECDC4'
                    ))
                    fig.update_layout(
                        polar=dict(radialaxis=dict(visible=True, range=[0, 100])),
                        height=400,
                        paper_bgcolor='#1a1a1a',
                        font=dict(color='white')
                    )
                    st.plotly_chart(fig, use_container_width=True)

                    # Bar
                    fig2 = go.Figure([
                        go.Bar(name=p1['name'], x=labels, y=v1, marker_color='#FF6B6B'),
                        go.Bar(name=p2['name'], x=labels, y=v2, marker_color='#4ECDC4')
                    ])
                    fig2.update_layout(barmode='group', height=300, paper_bgcolor='#1a1a1a', font=dict(color='white'))
                    st.plotly_chart(fig2, use_container_width=True)

                    # Table
                    st.dataframe({"Statystyka": labels, p1['name']: v1, p2['name']: v2}, hide_index=True)
                else:
                    st.warning("Brak danych")
else:
    st.info("👆 Wybierz dwóch graczy z list powyżej")
