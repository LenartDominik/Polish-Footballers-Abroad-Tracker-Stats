"""Polish Footballers Abroad Tracker - Streamlit Frontend."""

import os
import requests
from typing import Optional, List

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000/api/v1")
st.set_page_config(
    page_title="Polish Footballers Abroad Tracker",
    page_icon="⚽",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS
st.markdown("""
<style>
    .search-bar {
        position: sticky;
        top: 0;
        z-index: 100;
        background: white;
        padding: 1rem;
        border-bottom: 1px solid #eee;
    }
    .player-card {
        padding: 1rem;
        border-radius: 0.5rem;
        border: 1px solid #eee;
        margin-bottom: 1rem;
    }
    .stat-value {
        font-size: 1.5rem;
        font-weight: bold;
        color: #1f77b4;
    }
</style>
""", unsafe_allow_html=True)


def fetch_players(
    name: Optional[str] = None,
    team: Optional[str] = None,
    league: Optional[str] = None,
    limit: int = 20,
) -> List[dict]:
    """Fetch players from API."""
    params = {"limit": limit}
    if name:
        params["name"] = name
    if team:
        params["team"] = team
    if league:
        params["league"] = league

    try:
        response = requests.get(f"{API_BASE_URL}/players/search", params=params)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        st.error(f"Error fetching players: {e}")
        return []


def fetch_top_players(season: str = "2025/26", limit: int = 10) -> List[dict]:
    """Fetch top players from API."""
    try:
        response = requests.get(
            f"{API_BASE_URL}/players/top",
            params={"season": season, "limit": limit}
        )
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        st.error(f"Error fetching top players: {e}")
        return []


def fetch_top_week(limit: int = 5) -> List[dict]:
    """Fetch top players of the week."""
    try:
        response = requests.get(
            f"{API_BASE_URL}/players/top_week",
            params={"limit": limit}
        )
        response.raise_for_status()
        return response.json()
    except requests.RequestException:
        return []


def fetch_player_stats(player_id: int, season: Optional[str] = None) -> Optional[dict]:
    """Fetch player statistics."""
    params = {}
    if season:
        params["season"] = season

    try:
        response = requests.get(
            f"{API_BASE_URL}/players/{player_id}/stats",
            params=params
        )
        response.raise_for_status()
        return response.json()
    except requests.RequestException:
        return None


def fetch_leagues() -> List[dict]:
    """Fetch available leagues."""
    try:
        response = requests.get(f"{API_BASE_URL}/leagues")
        response.raise_for_status()
        return response.json()
    except requests.RequestException:
        return []


# ============================================
# SIDEBAR
# ============================================
st.sidebar.title("⚽ Polish Tracker")
st.sidebar.markdown("---")

# Global filters in sidebar
st.sidebar.subheader("Filtry")
player_query = st.sidebar.text_input("🔍 Szukaj piłkarza", placeholder="Wpisz nazwisko...")

# League filter (will be populated from API)
leagues = fetch_leagues()
league_names = ["Wszystkie"] + [l.get("name", "") for l in leagues if l.get("name")]
league_filter = st.sidebar.selectbox("Liga", league_names)

# ============================================
# MAIN CONTENT
# ============================================
st.title("🇵🇱 Polish Footballers Abroad Tracker")
st.markdown("Śledź polskich piłkarzy grających w najlepszych ligach świata!")

# Tabs
tab1, tab2, tab3 = st.tabs(["🏆 Dashboard", "🔍 Wyszukiwarka", "⚖️ Porównaj"])

with tab1:
    st.header("Top tygodnia")

    # Top week players
    top_week = fetch_top_week(5)
    if top_week:
        cols = st.columns(min(len(top_week), 5))
        for i, player in enumerate(top_week[:5]):
            with cols[i]:
                st.metric(
                    label=f"⚽ {player.get('player_name', 'N/A')}",
                    value=f"{player.get('goals', 0)} goli",
                    delta=f"{player.get('xg_per90', 0):.2f} xG/90"
                )

    st.markdown("---")
    st.info("🎯 Synchronizacja danych uruchomiona - sprawdź zakładkę Wyszukiwarka")

with tab2:
    st.header("Wyszukiwarka piłkarzy")

    # Search filters
    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        search_name = st.text_input("Nazwisko", placeholder="np. Lewandowski")
    with col2:
        search_team = st.text_input("Klub", placeholder="np. Barcelona")
    with col3:
        search_league = st.text_input("Liga", placeholder="np. La Liga")

    if st.button("🔍 Szukaj", type="primary"):
        if search_name or search_team or search_league:
            with st.spinner("Szukam..."):
                players = fetch_players(
                    name=search_name,
                    team=search_team,
                    league=search_league,
                )

            if players:
                st.success(f"Znaleziono {len(players)} piłkarzy")
                df = pd.DataFrame(players)
                st.dataframe(
                    df[["name", "position", "team", "league"]]
                    if all(col in df.columns for col in ["name", "position", "team", "league"])
                    else df,
                    use_container_width=True,
                )
            else:
                st.warning("Nie znaleziono piłkarzy spełniających kryteria")
        else:
            st.warning("Wprowadź przynajmniej jedno kryterium wyszukiwania")

with tab3:
    st.header("Porównywarka piłkarzy")
    st.info("🚧 Funkcja dostępna w wersji Premium")

    # Player comparison UI (placeholder)
    col1, col2 = st.columns(2)

    with col1:
        player1 = st.text_input("Piłkarz 1", placeholder="Wpisz nazwisko...", key="p1")

    with col2:
        player2 = st.text_input("Piłkarz 2", placeholder="Wpisz nazwisko...", key="p2")

    if player1 and player2:
        st.warning("⚠️ Porównywanie dostępne tylko dla tej samej pozycji (FW vs FW, GK vs GK)")

# ============================================
# LEGEND
# ============================================
with st.expander("📊 Legenda statystyk"):
    st.markdown("""
    - **xG (Expected Goals)**: Szansa na strzelenie gola (0-1). Im wyższe, tym lepsza okazja.
    - **xA (Expected Assists)**: Szansa na asystę przy akcji (0-1).
    - **xG/90**: Expected Goals na 90 minut - pozwala porównywać piłkarzy z różną liczbą minut.
    - **npxG**: xG bez rzutów karnych (bardziej obiektywne dla porównań).
    - **Save% (Bramkarze)**: Procent obronionych strzałów na bramkę.
    - **Clean Sheet**: Mecze bez puszczonego gola.
    """)
