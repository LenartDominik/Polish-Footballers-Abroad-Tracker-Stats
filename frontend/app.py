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

# Custom CSS for dark theme stats tables
st.markdown("""
<style>
    .stats-container {
        background-color: #1a1a1a;
        border-radius: 10px;
        padding: 15px;
        margin: 5px;
        min-height: 300px;
    }
    .stats-header {
        color: #ffffff;
        font-size: 1.1rem;
        font-weight: 600;
        margin-bottom: 15px;
        padding-bottom: 10px;
        border-bottom: 1px solid #333;
    }
    .stats-table {
        width: 100%;
        border-collapse: collapse;
    }
    .stats-table th {
        color: #888;
        font-size: 0.75rem;
        text-transform: uppercase;
        text-align: left;
        padding: 8px 5px;
        border-bottom: 1px solid #333;
    }
    .stats-table td {
        color: #fff;
        font-size: 1.3rem;
        font-weight: bold;
        padding: 10px 5px;
    }
    .stats-label {
        color: #888;
        font-size: 0.8rem;
    }
    .details-section {
        margin-top: 15px;
        padding-top: 10px;
        border-top: 1px solid #333;
    }
    .detail-row {
        display: flex;
        justify-content: space-between;
        padding: 5px 0;
        color: #ccc;
        font-size: 0.9rem;
    }
    .detail-value {
        color: #fff;
        font-weight: 500;
    }
    .subheader {
        color: #666;
        font-size: 0.75rem;
        margin-top: -5px;
        margin-bottom: 10px;
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


def fetch_player_detailed_stats(player_id: int, season: Optional[str] = None) -> Optional[dict]:
    """Fetch player detailed statistics with competition breakdown."""
    params = {}
    if season:
        params["season"] = season

    try:
        response = requests.get(
            f"{API_BASE_URL}/players/{player_id}/detailed-stats",
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


def fetch_filter_options() -> dict:
    """Fetch filter options for autocomplete (names, teams, leagues)."""
    try:
        response = requests.get(f"{API_BASE_URL}/players/filters")
        response.raise_for_status()
        return response.json()
    except requests.RequestException:
        return {"names": [], "teams": [], "leagues": []}


# ============================================
# SIDEBAR
# ============================================
st.sidebar.title("⚽ Polish Tracker")
st.sidebar.markdown("---")

# Global filters in sidebar
st.sidebar.subheader("Filtry")
player_query = st.sidebar.text_input("🔍 Search player", placeholder="Enter name...")

# League filter (will be populated from API)
leagues = fetch_leagues()
league_names = ["All"] + [l.get("name", "") for l in leagues if l.get("name")]
league_filter = st.sidebar.selectbox("League", league_names)

# ============================================
# MAIN CONTENT
# ============================================
st.title("🇵🇱 Polish Footballers Abroad Tracker")
st.markdown("Track Polish footballers playing in the world's top leagues!")

# Tabs
tab1, tab2, tab3 = st.tabs(["🏆 Dashboard", "🔍 Search", "⚖️ Compare"])

with tab1:
    st.header("Top of the Week")

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
    st.info("🎯 Data sync running - check the Search tab")

with tab2:
    st.header("Player Search")

    # Fetch filter options for autocomplete
    filter_options = fetch_filter_options()

    # Search filters with autocomplete
    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        name_options = [""] + filter_options.get("names", [])
        search_name = st.selectbox("Name", name_options, index=0, placeholder="Select or type...")
    with col2:
        team_options = [""] + filter_options.get("teams", [])
        search_team = st.selectbox("Club", team_options, index=0, placeholder="Select or type...")
    with col3:
        league_options = [""] + filter_options.get("leagues", [])
        search_league = st.selectbox("League", league_options, index=0, placeholder="Select or type...")

    if st.button("🔍 Search", type="primary"):
        if search_name or search_team or search_league:
            with st.spinner("Searching..."):
                players = fetch_players(
                    name=search_name if search_name else None,
                    team=search_team if search_team else None,
                    league=search_league if search_league else None,
                )

            if players:
                st.success(f"Found {len(players)} players")
                st.session_state["search_results"] = players
                # Reset player selection when new search is performed
                if "player_select" in st.session_state:
                    del st.session_state["player_select"]
            else:
                st.warning("No players found matching criteria")
                st.session_state["search_results"] = []
        else:
            st.warning("Enter at least one search criterion")

    # Player selection and detailed stats display
    if "search_results" in st.session_state and st.session_state["search_results"]:
        players = st.session_state["search_results"]

        # Build options with GK indicator
        player_options = {}
        for p in players:
            label = f"{p['name']} ({p.get('team', 'N/A')})"
            if p.get('position') == 'GK':
                label = f"🧤 {label}"
            player_options[label] = p

        selected = st.selectbox("Select player to view details:", options=list(player_options.keys()), key="player_select")
        selected_player = player_options[selected]

        # Season selector
        season = st.selectbox("Season", ["2025/26", "2024/25", "2023/24"], key="stats_season")

        # Fetch detailed stats
        with st.spinner("Loading stats..."):
            detailed_stats = fetch_player_detailed_stats(selected_player["id"], season)

        if detailed_stats:
            st.markdown("---")

            # Header with GK badge if applicable
            is_gk = detailed_stats.get("player_position") == "GK"
            header_text = f"📊 {detailed_stats['player_name']}"
            if is_gk:
                header_text += " 🧤 Goalkeeper"
            header_text += f" - {detailed_stats['player_team']}"
            st.subheader(header_text)

            # 4 columns: League | European | Domestic | Total
            col1, col2, col3, col4 = st.columns(4)

            # Helper to display stats column in card style
            def display_comp_stats(col, icon: str, title: str, subtitle: str, stats: dict, is_gk: bool, details_list=None):
                with col:
                    # Card container with dark theme
                    st.markdown(f"""
                    <div style="background-color: #1a1a1a; border-radius: 10px; padding: 15px; margin-bottom: 10px;">
                        <div style="font-size: 1.1rem; font-weight: 600; color: #fff; margin-bottom: 2px;">{icon} {title}</div>
                        <div style="font-size: 0.75rem; color: #666; margin-bottom: 12px;">{subtitle}</div>
                    """, unsafe_allow_html=True)

                    if stats is None:
                        st.markdown('<div style="color: #666; text-align: center; padding: 20px;">No data</div>', unsafe_allow_html=True)
                        st.markdown("</div>", unsafe_allow_html=True)
                        return

                    # Main stats table - DIFFERENT for GK vs Field Players
                    if is_gk:
                        # Goalkeeper stats
                        st.markdown("""
                        <table style="width: 100%; border-collapse: collapse;">
                            <tr style="border-bottom: 1px solid #333;">
                                <th style="color: #888; font-size: 0.7rem; text-transform: uppercase; padding: 5px 0; text-align: center;">Games</th>
                                <th style="color: #888; font-size: 0.7rem; text-transform: uppercase; padding: 5px 0; text-align: center;">CS</th>
                                <th style="color: #888; font-size: 0.7rem; text-transform: uppercase; padding: 5px 0; text-align: center;">GA</th>
                            </tr>
                            <tr>
                                <td style="color: #fff; font-size: 1.4rem; font-weight: bold; padding: 8px 0; text-align: center;">{}</td>
                                <td style="color: #fff; font-size: 1.4rem; font-weight: bold; padding: 8px 0; text-align: center;">{}</td>
                                <td style="color: #fff; font-size: 1.4rem; font-weight: bold; padding: 8px 0; text-align: center;">{}</td>
                            </tr>
                        </table>
                        """.format(
                            stats.get("matches_total", 0),
                            stats.get("clean_sheets", 0) or 0,
                            stats.get("goals_against", 0) or 0
                        ), unsafe_allow_html=True)
                    else:
                        # Field player stats
                        st.markdown("""
                        <table style="width: 100%; border-collapse: collapse;">
                            <tr style="border-bottom: 1px solid #333;">
                                <th style="color: #888; font-size: 0.7rem; text-transform: uppercase; padding: 5px 0; text-align: center;">Games</th>
                                <th style="color: #888; font-size: 0.7rem; text-transform: uppercase; padding: 5px 0; text-align: center;">Goals</th>
                                <th style="color: #888; font-size: 0.7rem; text-transform: uppercase; padding: 5px 0; text-align: center;">Assists</th>
                            </tr>
                            <tr>
                                <td style="color: #fff; font-size: 1.4rem; font-weight: bold; padding: 8px 0; text-align: center;">{}</td>
                                <td style="color: #fff; font-size: 1.4rem; font-weight: bold; padding: 8px 0; text-align: center;">{}</td>
                                <td style="color: #fff; font-size: 1.4rem; font-weight: bold; padding: 8px 0; text-align: center;">{}</td>
                            </tr>
                        </table>
                        """.format(
                            stats.get("matches_total", 0),
                            stats.get("goals", 0),
                            stats.get("assists", 0)
                        ), unsafe_allow_html=True)

                    # Rating
                    rating = stats.get("rating", 0)
                    st.markdown(f"""
                    <div style="margin-top: 8px; color: #888; font-size: 0.8rem;">
                        Rating: <span style="color: #fff; font-weight: 500;">{rating:.2f}</span>
                    </div>
                    """, unsafe_allow_html=True)

                    # Details section (expandable)
                    minutes = stats.get("minutes_played", 0)
                    starts = stats.get("matches_started", 0)

                    with st.expander("📋 Details"):
                        if is_gk:
                            # Goalkeeper details
                            saves = stats.get("saves", 0) or 0
                            save_pct = stats.get("save_percentage", 0) or 0
                            st.markdown(f"""
                            <div style="color: #ccc; font-size: 0.85rem;">
                                <div style="display: flex; justify-content: space-between; padding: 4px 0;">
                                    <span>Starts</span>
                                    <span style="color: #fff; font-weight: 500;">{starts}</span>
                                </div>
                                <div style="display: flex; justify-content: space-between; padding: 4px 0;">
                                    <span>Minutes</span>
                                    <span style="color: #fff; font-weight: 500;">{minutes:,}</span>
                                </div>
                                <div style="display: flex; justify-content: space-between; padding: 4px 0;">
                                    <span>Saves</span>
                                    <span style="color: #fff; font-weight: 500;">{saves}</span>
                                </div>
                                <div style="display: flex; justify-content: space-between; padding: 4px 0;">
                                    <span>Save %</span>
                                    <span style="color: #fff; font-weight: 500;">{save_pct:.1f}%</span>
                                </div>
                            </div>
                            """, unsafe_allow_html=True)
                        else:
                            # Field player details
                            g_per90 = stats.get("g_per90", 0) or 0
                            a_per90 = stats.get("a_per90", 0) or 0
                            ga_per90 = g_per90 + a_per90
                            st.markdown(f"""
                            <div style="color: #ccc; font-size: 0.85rem;">
                                <div style="display: flex; justify-content: space-between; padding: 4px 0;">
                                    <span>Starts</span>
                                    <span style="color: #fff; font-weight: 500;">{starts}</span>
                                </div>
                                <div style="display: flex; justify-content: space-between; padding: 4px 0;">
                                    <span>Minutes</span>
                                    <span style="color: #fff; font-weight: 500;">{minutes:,}</span>
                                </div>
                                <div style="display: flex; justify-content: space-between; padding: 4px 0;">
                                    <span>G+A/90</span>
                                    <span style="color: #fff; font-weight: 500;">{ga_per90:.2f}</span>
                                </div>
                            </div>
                            """, unsafe_allow_html=True)

                        # Show competition names if multiple
                        if details_list and len(details_list) > 1:
                            st.markdown('<div style="margin-top: 8px; padding-top: 8px; border-top: 1px solid #333; color: #666; font-size: 0.75rem;">', unsafe_allow_html=True)
                            for d in details_list:
                                st.markdown(f"• {d.get('competition_name', 'N/A')}: {d.get('matches_total', 0)} apps")
                            st.markdown('</div>', unsafe_allow_html=True)

                    st.markdown("</div>", unsafe_allow_html=True)

            # Display columns
            display_comp_stats(col1, "🏆", "League Stats", "2025/26", detailed_stats.get("league_stats"), is_gk)

            european_list = detailed_stats.get("european_stats", [])
            european_combined = None
            if european_list:
                eur_saves = sum(e.get("saves", 0) or 0 for e in european_list)
                eur_ga = sum(e.get("goals_against", 0) or 0 for e in european_list)
                eur_save_pct = round((eur_saves / (eur_saves + eur_ga)) * 100, 1) if (eur_saves + eur_ga) > 0 else 0
                european_combined = {
                    "matches_total": sum(e.get("matches_total", 0) for e in european_list),
                    "minutes_played": sum(e.get("minutes_played", 0) for e in european_list),
                    "matches_started": sum(e.get("matches_started", 0) for e in european_list),
                    "goals": sum(e.get("goals", 0) for e in european_list),
                    "assists": sum(e.get("assists", 0) for e in european_list),
                    "rating": sum(e.get("rating", 0) for e in european_list) / len(european_list) if european_list else 0,
                    "g_per90": sum(e.get("goals", 0) for e in european_list) * 90 / max(1, sum(e.get("minutes_played", 0) for e in european_list)),
                    "a_per90": sum(e.get("assists", 0) for e in european_list) * 90 / max(1, sum(e.get("minutes_played", 0) for e in european_list)),
                    "clean_sheets": sum(e.get("clean_sheets", 0) or 0 for e in european_list),
                    "saves": eur_saves,
                    "goals_against": eur_ga,
                    "save_percentage": eur_save_pct,
                }
            display_comp_stats(col2, "🌍", "European Cups", "2025/26", european_combined, is_gk, european_list)

            domestic_list = detailed_stats.get("domestic_stats", [])
            domestic_combined = None
            if domestic_list:
                domestic_combined = {
                    "matches_total": sum(d.get("matches_total", 0) for d in domestic_list),
                    "minutes_played": sum(d.get("minutes_played", 0) for d in domestic_list),
                    "matches_started": sum(d.get("matches_started", 0) for d in domestic_list),
                    "goals": sum(d.get("goals", 0) for d in domestic_list),
                    "assists": sum(d.get("assists", 0) for d in domestic_list),
                    "rating": sum(d.get("rating", 0) for d in domestic_list) / len(domestic_list) if domestic_list else 0,
                    "g_per90": sum(d.get("goals", 0) for d in domestic_list) * 90 / max(1, sum(d.get("minutes_played", 0) for d in domestic_list)),
                    "a_per90": sum(d.get("assists", 0) for d in domestic_list) * 90 / max(1, sum(d.get("minutes_played", 0) for d in domestic_list)),
                    "clean_sheets": sum(d.get("clean_sheets", 0) or 0 for d in domestic_list),
                    "saves": sum(d.get("saves", 0) or 0 for d in domestic_list),
                    "goals_against": sum(d.get("goals_against", 0) or 0 for d in domestic_list),
                    "save_percentage": sum(d.get("save_percentage", 0) or 0 for d in domestic_list) / len(domestic_list) if domestic_list else 0,
                }
            display_comp_stats(col3, "🏆", "Domestic Cups", "2025/26", domestic_combined, is_gk, domestic_list)

            total = detailed_stats.get("total")
            total_subtitle = "Club competitions only"
            display_comp_stats(col4, "📊", "Season Total", total_subtitle, total, is_gk)

        else:
            st.warning(f"No stats available for season {season}")

with tab3:
    st.header("Player Comparison")
    st.info("🚧 Feature available in Premium version")

    # Player comparison UI (placeholder)
    col1, col2 = st.columns(2)

    with col1:
        player1 = st.text_input("Player 1", placeholder="Enter name...", key="p1")

    with col2:
        player2 = st.text_input("Player 2", placeholder="Enter name...", key="p2")

    if player1 and player2:
        st.warning("⚠️ Comparison available only for same position (FW vs FW, GK vs GK)")

# ============================================
# LEGEND
# ============================================
with st.expander("📊 Stats Legend"):
    st.markdown("""
    - **G/90**: Goals per 90 minutes - allows comparing players with different minutes played.
    - **A/90**: Assists per 90 minutes.
    - **G+A/90**: Goals + Assists per 90 minutes.
    - **CS (Goalkeepers)**: Clean Sheets - matches without conceding a goal.
    - **GA (Goalkeepers)**: Goals Against - goals conceded.
    - **Save% (Goalkeepers)**: Percentage of shots saved.
    - **Rating**: Average match rating (1-10).
    """)
