"""Polish Footballers Abroad Tracker - Streamlit Frontend."""

import os
import requests
from typing import Optional, List

import streamlit as st
import plotly.graph_objects as go
from dotenv import load_dotenv

from utils.theme import get_theme_css, render_header, COLORS
from translations import t, language_selector, get_position_display, clean_team_name

# Load environment variables
load_dotenv()

# Configuration
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000/api/v1")
st.set_page_config(
    page_title="Polish Footballers Abroad",
    page_icon="⚽",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Apply theme CSS
st.markdown(get_theme_css(), unsafe_allow_html=True)

# Language selector (top of sidebar)
language_selector()


def fetch_players(
    name: Optional[str] = None,
    team: Optional[str] = None,
    league: Optional[str] = None,
    limit: int = 20,
) -> List[dict]:
    """Fetch players from API."""
    params: dict[str, str | int] = {"limit": limit}
    if name:
        params["name"] = name
    if team:
        params["team"] = team
    if league:
        params["league"] = league

    try:
        # Use /players/search only when filters are provided, otherwise /players/
        if name or team or league:
            response = requests.get(f"{API_BASE_URL}/players/search", params=params)
        else:
            response = requests.get(f"{API_BASE_URL}/players/", params=params)
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


def fetch_player_heatmap(player_id: int, season: str = "2025/26") -> Optional[dict]:
    """Fetch player heatmap position data."""
    try:
        response = requests.get(
            f"{API_BASE_URL}/players/{player_id}/heatmap",
            params={"season": season}
        )
        response.raise_for_status()
        return response.json()
    except requests.RequestException:
        return None


import numpy as np


def interpret_position(x: float, y: float) -> str:
    """Interpret normalized position coordinates to human-readable position.

    X: 0=own goal, 1=opponent goal (attack direction)
    Y: 0=right sideline, 1=left sideline (from viewer perspective)
    """
    # Y interpretation
    if y < 0.35:
        side = t("right_side")
    elif y > 0.65:
        side = t("left_side")
    else:
        side = t("center_side")

    # X interpretation
    if x < 0.35:
        depth = t("defensive")
    elif x > 0.65:
        depth = t("attacking")
    else:
        depth = t("midfield_zone")

    return f"{depth} {side}"


def get_position_side(y: float) -> str:
    """Get just the side (Left/Center/Right) from Y coordinate."""
    if y < 0.35:
        return t("right_side")
    elif y > 0.65:
        return t("left_side")
    else:
        return t("center_side")


def create_heatmap_figure(positions: List[dict], player_name: str) -> go.Figure:
    """Create a pitch heatmap visualization from position data."""
    if not positions:
        fig = go.Figure()
        fig.add_annotation(
            text=t("no_position_data_available"),
            xref="paper", yref="paper",
            x=0.5, y=0.5, showarrow=False,
            font=dict(size=16, color="#888")
        )
        return fig

    # Extract positions
    x = [p["pos_x"] for p in positions]
    y = [p["pos_y"] for p in positions]
    weights = [p.get("minutes_played", 1) for p in positions]

    # Create 2D histogram for density (20x20 grid)
    x_bins = np.linspace(0, 1, 21)
    y_bins = np.linspace(0, 1, 21)

    heatmap, xedges, yedges = np.histogram2d(x, y, bins=[x_bins, y_bins], weights=weights)

    # Create figure
    fig = go.Figure()

    # Add heatmap trace
    fig.add_trace(go.Heatmap(
        z=heatmap.T,
        x=xedges[:-1],
        y=yedges[:-1],
        colorscale=[
            [0, "rgba(0,0,0,0)"],
            [0.2, "rgba(0,100,0,0.3)"],
            [0.5, "rgba(255,165,0,0.5)"],
            [0.8, "rgba(255,69,0,0.7)"],
            [1, "rgba(255,0,0,0.9)"]
        ],
        showscale=True,
        colorbar=dict(title=dict(text=t("minutes_label"), font=dict(color="#888")), tickfont=dict(color="#888")),
        hovertemplate="X: %{x:.2f}<br>Y: %{y:.2f}<br>Minutes: %{z:.0f}<extra></extra>",
    ))

    # Add pitch outline
    fig.add_shape(type="rect", x0=0, y0=0, x1=1, y1=1, line=dict(color="#444", width=2))

    # Add penalty areas
    fig.add_shape(type="rect", x0=0, y0=0.21, x1=0.17, y1=0.79, line=dict(color="#444", width=1))
    fig.add_shape(type="rect", x0=0.83, y0=0.21, x1=1, y1=0.79, line=dict(color="#444", width=1))

    # Add goal areas
    fig.add_shape(type="rect", x0=0, y0=0.36, x1=0.06, y1=0.64, line=dict(color="#444", width=1))
    fig.add_shape(type="rect", x0=0.94, y0=0.36, x1=1, y1=0.64, line=dict(color="#444", width=1))

    # Add center line
    fig.add_shape(type="line", x0=0.5, y0=0, x1=0.5, y1=1, line=dict(color="#444", width=1))

    # Add center circle
    fig.add_shape(type="circle", x0=0.35, y0=0.35, x1=0.65, y1=0.65, line=dict(color="#444", width=1))

    # Update layout
    fig.update_layout(
        title=dict(text=f"📍 {t('position_zones_title', name=player_name)}"),
        xaxis=dict(showgrid=False, showticklabels=False, zeroline=False),
        yaxis=dict(showgrid=False, showticklabels=False, zeroline=False, scaleanchor="x", scaleratio=0.7),
        width=500,
        height=350,
        margin=dict(l=10, r=10, t=40, b=10),
    )

    return fig


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


def aggregate_stats_list(stats_list: list[dict]) -> dict | None:
    """Aggregate a list of competition stats into combined stats dict."""
    if not stats_list:
        return None

    total_minutes = sum(s.get("minutes_played", 0) for s in stats_list)
    saves = sum(s.get("saves", 0) or 0 for s in stats_list)
    ga = sum(s.get("goals_against", 0) or 0 for s in stats_list)
    save_pct = round((saves / (saves + ga)) * 100, 1) if (saves + ga) > 0 else 0

    return {
        "matches_total": sum(s.get("matches_total", 0) for s in stats_list),
        "minutes_played": total_minutes,
        "matches_started": sum(s.get("matches_started", 0) for s in stats_list),
        "goals": sum(s.get("goals", 0) for s in stats_list),
        "assists": sum(s.get("assists", 0) for s in stats_list),
        "rating": sum(s.get("rating", 0) for s in stats_list) / len(stats_list),
        "g_per90": sum(s.get("goals", 0) for s in stats_list) * 90 / max(1, total_minutes),
        "a_per90": sum(s.get("assists", 0) for s in stats_list) * 90 / max(1, total_minutes),
        "clean_sheets": sum(s.get("clean_sheets", 0) or 0 for s in stats_list),
        "saves": saves,
        "goals_against": ga,
        "save_percentage": save_pct,
    }


def get_cached_filter_options() -> dict:
    """Get filter options, cached in session state to avoid duplicate API calls."""
    if "filter_options" not in st.session_state:
        st.session_state["filter_options"] = fetch_filter_options()
    return st.session_state["filter_options"]


def display_comp_stats(col, icon: str, title: str, subtitle: str, stats: dict | None, is_gk: bool, details_list=None):
    """Display stats column in card style - used by both Dashboard and Search tabs."""
    bg_card = COLORS['bg_card']
    text_primary = COLORS['text_primary']
    text_secondary = COLORS['text_secondary']
    text_muted = COLORS['text_muted']
    border_color = COLORS['border_color']

    with col:
        st.markdown(f"""
        <div style="background-color: {bg_card}; border: 1px solid {border_color}; border-radius: 10px; padding: 15px; margin-bottom: 10px;">
            <div style="font-size: 1.1rem; font-weight: 600; color: {text_primary}; margin-bottom: 2px;">{icon} {title}</div>
            <div style="font-size: 0.75rem; color: {text_muted}; margin-bottom: 12px;">{subtitle}</div>
        """, unsafe_allow_html=True)

        if stats is None:
            st.markdown(f'<div style="color: {text_muted}; text-align: center; padding: 20px;">{t("no_data")}</div>', unsafe_allow_html=True)
            st.markdown("</div>", unsafe_allow_html=True)
            return

        if is_gk:
            st.markdown(f"""
            <table style="width: 100%; border-collapse: collapse;">
                <tr style="border-bottom: 1px solid {border_color};">
                    <th style="color: {text_muted}; font-size: 0.7rem; text-transform: uppercase; padding: 5px 0; text-align: center;">{t("games")}</th>
                    <th style="color: {text_muted}; font-size: 0.7rem; text-transform: uppercase; padding: 5px 0; text-align: center;">{t("cs")}</th>
                    <th style="color: {text_muted}; font-size: 0.7rem; text-transform: uppercase; padding: 5px 0; text-align: center;">{t("ga")}</th>
                </tr>
                <tr>
                    <td style="color: {text_primary}; font-size: 1.4rem; font-weight: bold; padding: 8px 0; text-align: center;">{{}}</td>
                    <td style="color: {text_primary}; font-size: 1.4rem; font-weight: bold; padding: 8px 0; text-align: center;">{{}}</td>
                    <td style="color: {text_primary}; font-size: 1.4rem; font-weight: bold; padding: 8px 0; text-align: center;">{{}}</td>
                </tr>
            </table>
            """.format(
                stats.get("matches_total", 0),
                stats.get("clean_sheets", 0) or 0,
                stats.get("goals_against", 0) or 0
            ), unsafe_allow_html=True)
        else:
            st.markdown(f"""
            <table style="width: 100%; border-collapse: collapse;">
                <tr style="border-bottom: 1px solid {border_color};">
                    <th style="color: {text_muted}; font-size: 0.7rem; text-transform: uppercase; padding: 5px 0; text-align: center;">{t("games")}</th>
                    <th style="color: {text_muted}; font-size: 0.7rem; text-transform: uppercase; padding: 5px 0; text-align: center;">{t("goals")}</th>
                    <th style="color: {text_muted}; font-size: 0.7rem; text-transform: uppercase; padding: 5px 0; text-align: center;">{t("assists")}</th>
                </tr>
                <tr>
                    <td style="color: {text_primary}; font-size: 1.4rem; font-weight: bold; padding: 8px 0; text-align: center;">{{}}</td>
                    <td style="color: {text_primary}; font-size: 1.4rem; font-weight: bold; padding: 8px 0; text-align: center;">{{}}</td>
                    <td style="color: {text_primary}; font-size: 1.4rem; font-weight: bold; padding: 8px 0; text-align: center;">{{}}</td>
                </tr>
            </table>
            """.format(
                stats.get("matches_total", 0),
                stats.get("goals", 0),
                stats.get("assists", 0)
            ), unsafe_allow_html=True)

        rating = stats.get("rating", 0)
        st.markdown(f"""
        <div style="margin-top: 8px; color: {text_muted}; font-size: 0.8rem;">
            {t("rating")}: <span style="color: {text_primary}; font-weight: 500;">{rating:.2f}</span>
        </div>
        """, unsafe_allow_html=True)

        minutes = stats.get("minutes_played", 0)
        starts = stats.get("matches_started", 0)

        with st.expander(t("details")):
            if is_gk:
                saves = stats.get("saves", 0) or 0
                save_pct = stats.get("save_percentage", 0) or 0
                st.markdown(f"""
                <div style="color: {text_secondary}; font-size: 0.85rem;">
                    <div style="display: flex; justify-content: space-between; padding: 4px 0;">
                        <span>{t("starts")}</span>
                        <span style="color: {text_primary}; font-weight: 500;">{starts}</span>
                    </div>
                    <div style="display: flex; justify-content: space-between; padding: 4px 0;">
                        <span>{t("minutes")}</span>
                        <span style="color: {text_primary}; font-weight: 500;">{minutes:,}</span>
                    </div>
                    <div style="display: flex; justify-content: space-between; padding: 4px 0;">
                        <span>{t("saves")}</span>
                        <span style="color: {text_primary}; font-weight: 500;">{saves}</span>
                    </div>
                    <div style="display: flex; justify-content: space-between; padding: 4px 0;">
                        <span>{t("save_pct")}</span>
                        <span style="color: {text_primary}; font-weight: 500;">{save_pct:.1f}%</span>
                    </div>
                </div>
                """, unsafe_allow_html=True)
            else:
                g_per90 = stats.get("g_per90", 0) or 0
                a_per90 = stats.get("a_per90", 0) or 0
                ga_per90 = g_per90 + a_per90
                st.markdown(f"""
                <div style="color: {text_secondary}; font-size: 0.85rem;">
                    <div style="display: flex; justify-content: space-between; padding: 4px 0;">
                        <span>{t("starts")}</span>
                        <span style="color: {text_primary}; font-weight: 500;">{starts}</span>
                    </div>
                    <div style="display: flex; justify-content: space-between; padding: 4px 0;">
                        <span>{t("minutes")}</span>
                        <span style="color: {text_primary}; font-weight: 500;">{minutes:,}</span>
                    </div>
                    <div style="display: flex; justify-content: space-between; padding: 4px 0;">
                        <span>{t("g_per90")}</span>
                        <span style="color: {text_primary}; font-weight: 500;">{g_per90:.2f}</span>
                    </div>
                    <div style="display: flex; justify-content: space-between; padding: 4px 0;">
                        <span>{t("a_per90")}</span>
                        <span style="color: {text_primary}; font-weight: 500;">{a_per90:.2f}</span>
                    </div>
                    <div style="display: flex; justify-content: space-between; padding: 4px 0;">
                        <span>{t("ga_per90")}</span>
                        <span style="color: {text_primary}; font-weight: 500;">{ga_per90:.2f}</span>
                    </div>
                </div>
                """, unsafe_allow_html=True)

            if details_list and len(details_list) > 1:
                st.markdown(f'<div style="margin-top: 8px; padding-top: 8px; border-top: 1px solid {border_color}; color: {text_muted}; font-size: 0.75rem;">', unsafe_allow_html=True)
                for d in details_list:
                    st.markdown(f"• {d.get('competition_name', 'N/A')}: {d.get('matches_total', 0)} {t('apps')}")
                st.markdown('</div>', unsafe_allow_html=True)

        st.markdown("</div>", unsafe_allow_html=True)


# ============================================
# SIDEBAR
# ============================================
st.sidebar.title(t("sidebar_title"))
st.sidebar.markdown("---")

# Global filters in sidebar
st.sidebar.subheader(t("filters"))

# Fetch filter options for autocomplete (cached)
filter_options = get_cached_filter_options()

# Track which filter was last changed
def on_player_change():
    st.session_state["active_filter"] = "player"

def on_club_change():
    st.session_state["active_filter"] = "club"

# Initialize active filter
if "active_filter" not in st.session_state:
    st.session_state["active_filter"] = None

# Player search with autocomplete
player_names = [""] + filter_options.get("names", [])
player_query = st.sidebar.selectbox(t("search_player"), player_names, index=0, placeholder="Type or select...", on_change=on_player_change)

# Club filter - clubs where Polish players play + option to type any club
club_options = [t("all")] + filter_options.get("teams", [])
club_filter = st.sidebar.selectbox(t("club"), club_options, index=0, placeholder="Type or select...", on_change=on_club_change)

# ============================================
# MAIN CONTENT
# ============================================
# Render header
render_header()

# Tabs
tab1, tab2, tab3, tab4 = st.tabs([t("tab_dashboard"), t("tab_search"), t("tab_compare"), t("tab_zones")])

with tab1:
    # Filters are MUTUALLY EXCLUSIVE - use whichever was last changed
    search_name = player_query if player_query else None
    search_club = club_filter if club_filter and club_filter != t("all") else None
    active_filter = st.session_state.get("active_filter")

    # Use the filter that was last changed
    if active_filter == "player" and search_name:
        with st.spinner(t("searching_for", name=search_name)):
            players = fetch_players(name=search_name, limit=10)
    elif active_filter == "club" and search_club:
        with st.spinner(t("loading_players_from", club=search_club)):
            players = fetch_players(team=search_club, limit=20)
    elif search_name:
        with st.spinner(t("searching_for", name=search_name)):
            players = fetch_players(name=search_name, limit=10)
    elif search_club:
        with st.spinner(t("loading_players_from", club=search_club)):
            players = fetch_players(team=search_club, limit=20)
    else:
        players = []

    if players:
        # Auto-select first player if only one result
        if len(players) == 1:
            selected_player = players[0]
        else:
            # Let user select from results
            player_options = {}
            for p in players:
                pos_display = get_position_display(p.get('position'))
                label = f"{p['name']} - {clean_team_name(p.get('team'))} ({pos_display})"
                player_options[label] = p

            selected = st.selectbox(t("select_player"), options=list(player_options.keys()), key="dashboard_player_select")
            selected_player = player_options[selected]

        # Season hardcoded to current
        season = "2025/26"

        # Fetch and display detailed stats
        with st.spinner(t("loading_stats")):
            detailed_stats = fetch_player_detailed_stats(selected_player["id"], season)

        if detailed_stats:
            st.markdown("---")

            # Header with GK badge if applicable
            is_gk = detailed_stats.get("player_position") == "GK"
            header_text = f"📊 {detailed_stats['player_name']}"
            if is_gk:
                header_text += f" {t('goalkeeper')}"
            header_text += f" - {clean_team_name(detailed_stats['player_team'])}"
            st.subheader(header_text)

            # 4 columns: League | European/Continental | Domestic | Total
            col1, col2, col3, col4 = st.columns(4)

            # Reuse display function from Search tab
            display_comp_stats(col1, "🏆", t("league"), "2025/26", detailed_stats.get("league_stats"), is_gk)

            # Handle European or Continental stats (depending on player)
            european_list = detailed_stats.get("european_stats", [])
            continental_list = detailed_stats.get("continental_stats", [])

            if continental_list:
                continental_combined = aggregate_stats_list(continental_list)
                display_comp_stats(col2, "🌏", t("afc_champions_league"), "2025/26", continental_combined, is_gk, continental_list)
            else:
                european_combined = aggregate_stats_list(european_list)
                display_comp_stats(col2, "🌍", t("european_cups"), "2025/26", european_combined, is_gk, european_list)
            domestic_list = detailed_stats.get("domestic_stats", [])
            domestic_combined = aggregate_stats_list(domestic_list)
            display_comp_stats(col3, "🏆", t("domestic_cups"), "2025/26", domestic_combined, is_gk, domestic_list)

            total = detailed_stats.get("total")
            total_subtitle = t("club_competitions_only")
            display_comp_stats(col4, "📊", t("season_total"), total_subtitle, total, is_gk)
        else:
            st.warning(t("no_stats_available", season=season))
    else:
        # Show warning based on which filter was active
        if active_filter == "player" and search_name:
            st.warning(t("no_players_found", name=search_name))
        elif active_filter == "club" and search_club:
            st.warning(t("no_players_in_club", club=search_club))
        elif search_name:
            st.warning(t("no_players_found", name=search_name))
        elif search_club:
            st.warning(t("no_players_in_club", club=search_club))
        else:
            st.info(t("use_filters"))

with tab2:
    st.markdown(f'<h2 style="text-align: center;">{t("player_search")}</h2>', unsafe_allow_html=True)

    # Use cached filter options
    filter_options = get_cached_filter_options()

    # Track which filter was last changed
    def on_name_change():
        st.session_state["search_active_filter"] = "name"

    def on_team_change():
        st.session_state["search_active_filter"] = "team"

    # Initialize active filter
    if "search_active_filter" not in st.session_state:
        st.session_state["search_active_filter"] = None

    # Search filters with autocomplete
    col1, col2 = st.columns([2, 1])
    with col1:
        name_options = [""] + filter_options.get("names", [])
        search_name = st.selectbox(t("name"), name_options, index=0, placeholder="Select or type...", on_change=on_name_change, key="search_name_select")
    with col2:
        team_options = [""] + filter_options.get("teams", [])
        search_team = st.selectbox(t("club"), team_options, index=0, placeholder="Select or type...", on_change=on_team_change, key="search_team_select")

    # Use only the filter that was last changed
    active_filter = st.session_state.get("search_active_filter")

    if active_filter == "name" and search_name:
        search_team = None
    elif active_filter == "team" and search_team:
        search_name = None

    # Auto-search when any filter is set
    if search_name or search_team:
        with st.spinner(t("searching")):
            players = fetch_players(
                name=search_name if search_name else None,
                team=search_team if search_team else None,
            )

        if players:
            # Auto-select first player if only one result
            if len(players) == 1:
                selected_player = players[0]
            else:
                # Let user select from results
                player_options = {}
                for p in players:
                    pos_display = get_position_display(p.get('position'))
                    label = f"{p['name']} - {clean_team_name(p.get('team'))} ({pos_display})"
                    player_options[label] = p

                selected = st.selectbox(t("select_player"), options=list(player_options.keys()), key="player_select")
                selected_player = player_options[selected]

            # Season hardcoded to current
            season = "2025/26"

            # Fetch detailed stats
            with st.spinner(t("loading_stats")):
                detailed_stats = fetch_player_detailed_stats(selected_player["id"], season)

            if detailed_stats:
                st.markdown("---")

                # Header with GK badge if applicable
                is_gk = detailed_stats.get("player_position") == "GK"
                header_text = f"📊 {detailed_stats['player_name']}"
                if is_gk:
                    header_text += f" {t('goalkeeper')}"
                header_text += f" - {clean_team_name(detailed_stats['player_team'])}"
                st.subheader(header_text)

                # 4 columns: League | European/Continental | Domestic | Total
                col1, col2, col3, col4 = st.columns(4)

                # Display columns
                display_comp_stats(col1, "🏆", t("league_stats"), "2025/26", detailed_stats.get("league_stats"), is_gk)

                # Handle European or Continental stats (depending on player)
                european_list = detailed_stats.get("european_stats", [])
                continental_list = detailed_stats.get("continental_stats", [])

                if continental_list:
                    continental_combined = aggregate_stats_list(continental_list)
                    display_comp_stats(col2, "🌏", t("afc_champions_league"), "2025/26", continental_combined, is_gk, continental_list)
                else:
                    european_combined = aggregate_stats_list(european_list)
                    display_comp_stats(col2, "🌍", t("european_cups"), "2025/26", european_combined, is_gk, european_list)

                domestic_list = detailed_stats.get("domestic_stats", [])
                domestic_combined = aggregate_stats_list(domestic_list)
                display_comp_stats(col3, "🏆", t("domestic_cups"), "2025/26", domestic_combined, is_gk, domestic_list)

                total = detailed_stats.get("total")
                total_subtitle = t("club_competitions_only")
                display_comp_stats(col4, "📊", t("season_total"), total_subtitle, total, is_gk)

            else:
                st.warning(t("no_stats_available", season=season))
        else:
            st.warning(t("no_players_criteria"))
    else:
        st.info(t("select_filter"))

with tab3:
    st.markdown(f'<h2 style="text-align: center;">{t("player_comparison")}</h2>', unsafe_allow_html=True)

    # Fetch all players
    all_players = fetch_players(limit=100)

    if not all_players:
        st.error(t("backend_not_running"))
    else:
        # Create options list with position display
        player_options = {}
        for p in all_players:
            team = p.get("team", "N/A")
            pos_display = get_position_display(p.get("position"))
            label = f"{p['name']} - {team} ({pos_display})"
            player_options[label] = p

        option_list = [t("select_placeholder")] + list(player_options.keys())

        col1, col2 = st.columns(2)

        with col1:
            sel1 = st.selectbox(t("player_1"), option_list, key="compare_p1_final")

        with col2:
            sel2 = st.selectbox(t("player_2"), option_list, key="compare_p2_final")

        # Season hardcoded to current
        season_cmp = "2025/26"

        # Check if players are selected
        if sel1 != t("select_placeholder") and sel2 != t("select_placeholder"):
            p1 = player_options[sel1]
            p2 = player_options[sel2]

            # Check if same player
            if p1['id'] == p2['id']:
                st.error(t("cannot_compare_self"))
            elif p1.get("position") != p2.get("position") and (p1.get("position") == "GK" or p2.get("position") == "GK"):
                st.error(t("cannot_compare_gk_field"))
            else:
                gk1 = p1.get("position") == "GK"
                gk2 = p2.get("position") == "GK"
                is_gk = gk1
                st.info(f"📅 {season_cmp} | {t('goalkeepers_label') if is_gk else t('field_players_label')} | {t('league_games_only')}")

                # Stats
                st.subheader(t("select_stats"))
                stats = []

                if is_gk:
                    x1, x2, x3 = st.columns(3)
                    with x1:
                        c1 = st.checkbox(t("saves"), True)
                        c2 = st.checkbox(t("save_pct"), True)
                        c3 = st.checkbox(t("clean_sheets"), True)
                    with x2:
                        c4 = st.checkbox(t("goals_against"), True)
                        c5 = st.checkbox(t("penalties_saved"), True)
                    with x3:
                        c6 = st.checkbox(t("matches"), True)
                        c7 = st.checkbox(t("minutes"), True)

                    if c1: stats.append((t("saves"), "saves"))
                    if c2: stats.append((t("save_pct"), "save_percentage"))
                    if c3: stats.append((t("clean_sheets"), "clean_sheets"))
                    if c4: stats.append((t("goals_against"), "goals_against"))
                    if c5: stats.append((t("penalties_saved"), "penalties_saved"))
                    if c6: stats.append((t("matches"), "matches_total"))
                    if c7: stats.append((t("minutes"), "minutes_played"))
                else:
                    x1, x2 = st.columns(2)
                    with x1:
                        c1 = st.checkbox(t("goals"), True)
                        c2 = st.checkbox(t("assists"), True)
                        c3 = st.checkbox(t("g_per90"), True)
                        c4 = st.checkbox(t("a_per90"), True)
                    with x2:
                        c5 = st.checkbox(t("matches"), True)
                        c6 = st.checkbox(t("minutes"), False)

                    if c1: stats.append((t("goals"), "goals"))
                    if c2: stats.append((t("assists"), "assists"))
                    if c3: stats.append((t("g_per90"), "g_per90"))
                    if c4: stats.append((t("a_per90"), "a_per90"))
                    if c5: stats.append((t("matches"), "matches_total"))
                    if c6: stats.append((t("minutes"), "minutes_played"))

                if st.button(t("compare_btn"), type="primary"):
                    if not stats:
                        st.warning(t("select_stats"))
                    else:
                        with st.spinner(t("searching")):
                            s1 = fetch_player_detailed_stats(p1["id"], season_cmp)
                            s2 = fetch_player_detailed_stats(p2["id"], season_cmp)

                        if s1 and s2:
                            t1 = s1.get("league_stats") or s1.get("total", {})
                            t2 = s2.get("league_stats") or s2.get("total", {})

                            labels = [x[0] for x in stats]
                            keys = [x[1] for x in stats]
                            v1 = [float(t1.get(k, 0) or 0) for k in keys]
                            v2 = [float(t2.get(k, 0) or 0) for k in keys]

                            st.markdown(f"### {p1['name']} vs {p2['name']}")

                            # Radar
                            n1, n2 = [], []
                            for i, (a, b) in enumerate(zip(v1, v2)):
                                mx = max(a, b) if max(a, b) > 0 else 1
                                if keys[i] in ["goals_against", "yellow_cards", "red_cards"]:
                                    n1.append((1 - a/mx) * 100)
                                    n2.append((1 - b/mx) * 100)
                                else:
                                    n1.append((a/mx) * 100)
                                    n2.append((b/mx) * 100)

                            fig = go.Figure()
                            fig.add_trace(go.Scatterpolar(r=n1+[n1[0]], theta=labels+[labels[0]], fill='toself', name=p1['name'], line_color='#FF6B6B'))
                            fig.add_trace(go.Scatterpolar(r=n2+[n2[0]], theta=labels+[labels[0]], fill='toself', name=p2['name'], line_color='#4ECDC4'))
                            fig.update_layout(polar=dict(radialaxis=dict(visible=True, range=[0,100])), height=400)
                            st.plotly_chart(fig, use_container_width=True)

                            # Bar
                            fig2 = go.Figure([
                                go.Bar(name=p1['name'], x=labels, y=v1, marker_color='#FF6B6B'),
                                go.Bar(name=p2['name'], x=labels, y=v2, marker_color='#4ECDC4')
                            ])
                            fig2.update_layout(barmode='group', height=300)
                            st.plotly_chart(fig2, use_container_width=True)

                            # Table
                            st.dataframe({"Stat": labels, p1['name']: v1, p2['name']: v2}, hide_index=True)
                        else:
                            st.warning(t("no_data_compare"))
        else:
            st.info(t("select_two_players"))

# ============================================
# TAB 4: HEATMAPS
# ============================================
with tab4:
    st.markdown(f'<h2 style="text-align: center;">{t("tab_zones")}</h2>', unsafe_allow_html=True)

    # Premium badge
    premium_text = t("premium_feature")
    st.markdown(f"""
    <div style="text-align: center; margin-bottom: 20px;">
        <span style="background: linear-gradient(90deg, #FFD700, #FFA500); color: #000; padding: 4px 12px;
                     border-radius: 12px; font-weight: bold; font-size: 0.8rem;">{premium_text}</span>
    </div>
    """, unsafe_allow_html=True)

    # Fetch all players for selection
    all_players = fetch_players(limit=100)

    if not all_players:
        st.error(t("backend_not_running"))
    else:
        # Filter out goalkeepers for heatmap selection
        field_players = [p for p in all_players if p.get("position") != "GK"]

        if not field_players:
            st.warning(t("no_field_players"))
        else:
            # Player selection
            player_options = {}
            for p in field_players:
                team = clean_team_name(p.get("team", "N/A"))
                pos_display = get_position_display(p.get("position"))
                label = f"{p['name']} - {team} ({pos_display})"
                player_options[label] = p

            selected = st.selectbox(
                t("select_player_label"),
                options=list(player_options.keys()),
                key="heatmap_player_select"
            )
            selected_player = player_options[selected]

            season = "2025/26"

            # Fetch heatmap data
            with st.spinner(t("loading_position_data")):
                heatmap_data = fetch_player_heatmap(selected_player["id"], season)

            if heatmap_data and heatmap_data.get("positions"):
                st.markdown("---")

                # Legend for users
                st.info(f"""
                {t('how_to_read_title')}
                {t('red_zones_desc')}
                {t('multiple_zones_desc')}
                {t('x_axis_desc')}
                {t('y_axis_desc')}

                {t('fewer_matches_title')}
                {t('fewer_matches_api')}
                {t('fewer_matches_detail')}
                {t('fewer_matches_note')}
                """)

                # Player header
                st.subheader(f"📍 {selected_player['name']}")
                st.caption(f"{clean_team_name(selected_player.get('team'))} | {get_position_display(selected_player.get('position'))} | {season}")

                # Create and display heatmap
                fig = create_heatmap_figure(
                    heatmap_data["positions"],
                    selected_player["name"]
                )
                st.plotly_chart(fig, use_container_width=True)

                # Stats summary
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric(t("matches"), heatmap_data["total_matches"])
                with col2:
                    total_minutes = sum(p.get("minutes_played", 0) for p in heatmap_data["positions"])
                    st.metric(t("total_minutes"), total_minutes)
                with col3:
                    avg_pos = heatmap_data.get("avg_position", {})
                    if avg_pos:
                        position_text = interpret_position(avg_pos.get('x', 0.5), avg_pos.get('y', 0.5))
                        st.metric(t("avg_position"), position_text)
                        st.caption(f"({avg_pos.get('x', 0):.2f}, {avg_pos.get('y', 0):.2f})")
                    else:
                        st.metric(t("avg_position"), "N/A")
                with col4:
                    positions = heatmap_data.get("positions", [])
                    left_count = sum(1 for p in positions if p.get('pos_y', 0.5) > 0.65)
                    center_count = sum(1 for p in positions if 0.35 <= p.get('pos_y', 0.5) <= 0.65)
                    right_count = sum(1 for p in positions if p.get('pos_y', 0.5) < 0.35)
                    st.metric(t("side_breakdown"), f"L:{left_count} C:{center_count} R:{right_count}")

                # Match breakdown expander
                with st.expander(f"📋 {heatmap_data['total_matches']} {t('matches_with_zone')}"):
                    for pos in heatmap_data["positions"][:10]:  # Show first 10
                        comp_icon = "🏆" if pos.get("competition_type") == "league" else "🌍" if pos.get("competition_type") == "european" else "🏅"
                        position_text = interpret_position(pos['pos_x'], pos['pos_y'])
                        side = get_position_side(pos['pos_y'])
                        st.markdown(
                            f"**{comp_icon} {pos.get('competition_name', 'Unknown')}** - "
                            f"📍 {position_text} ({side}) - "
                            f"{pos.get('minutes_played', 0)} min"
                        )
                    if heatmap_data["total_matches"] > 10:
                        st.markdown(t("and_more_matches", count=heatmap_data['total_matches'] - 10))
            else:
                st.info(f"""
                {t('no_position_data', name=selected_player['name'])}

                {t('sync_instruction')}
                """)

# ============================================
# LEGEND
# ============================================
with st.expander(t("stats_legend")):
    st.markdown(f"""
    {t('legend_g90')}
    {t('legend_a90')}
    {t('legend_ga90')}
    {t('legend_cs')}
    {t('legend_ga')}
    {t('legend_save_pct')}
    {t('legend_rating')}
    """)
