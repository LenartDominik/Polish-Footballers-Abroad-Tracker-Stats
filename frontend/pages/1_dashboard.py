"""Dashboard page - detailed stats and visualizations."""

import os

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests

import sys
sys.path.append('..')
from utils.theme import get_theme_css, render_header, theme_toggle, init_theme, apply_plotly_theme

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000/api/v1")

st.set_page_config(page_title="Dashboard", page_icon="📊", layout="wide")

# Theme setup
dark_mode = init_theme()
dark_mode = theme_toggle()
st.markdown(get_theme_css(dark_mode), unsafe_allow_html=True)

# Render header
render_header("Dashboard", "📊")

# Season hardcoded to current
season = "2025/26"

# Fetch top players
@st.cache_data(ttl=300)
def get_top_data(season: str):
    try:
        response = requests.get(
            f"{API_BASE_URL}/players/top",
            params={"season": season, "limit": 50}
        )
        response.raise_for_status()
        return response.json()
    except:
        return []

data = get_top_data(season)

if data:
    df = pd.DataFrame(data)

    # KPIs
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Players in DB", len(df))
    with col2:
        st.metric("Total Goals", df["goals"].sum() if "goals" in df else 0)
    with col3:
        st.metric("Avg xG/90", f"{df['xg_per90'].mean():.2f}" if "xg_per90" in df else "N/A")
    with col4:
        st.metric("Total Assists", df["assists"].sum() if "assists" in df else 0)

    st.markdown("---")

    # Charts
    tab1, tab2, tab3 = st.tabs(["Goals", "xG/90", "Assists"])

    with tab1:
        fig = px.bar(
            df.nlargest(15, "goals") if "goals" in df else df,
            x="player_name",
            y="goals",
            title="Top 15 Scorers",
            color="goals",
            color_continuous_scale="Reds",
        )
        fig = apply_plotly_theme(fig, dark_mode)
        st.plotly_chart(fig, use_container_width=True)

    with tab2:
        fig = px.scatter(
            df[df["minutes_played"] > 500] if "minutes_played" in df else df,
            x="xg_per90",
            y="goals",
            hover_data=["player_name"],
            title="xG/90 vs Goals (min 500 minutes)",
            labels={"xg_per90": "xG/90", "goals": "Goals"},
        )
        fig = apply_plotly_theme(fig, dark_mode)
        st.plotly_chart(fig, use_container_width=True)

    with tab3:
        fig = px.bar(
            df.nlargest(15, "assists") if "assists" in df else df,
            x="player_name",
            y="assists",
            title="Top 15 Assist Providers",
            color="assists",
            color_continuous_scale="Greens",
        )
        fig = apply_plotly_theme(fig, dark_mode)
        st.plotly_chart(fig, use_container_width=True)

else:
    st.info("No data - start backend and check API connection")
