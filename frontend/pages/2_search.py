"""Search page - advanced player search."""

import os

import streamlit as st
import pandas as pd
import requests

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000/api/v1")

st.set_page_config(page_title="Wyszukiwarka", page_icon="🔍", layout="wide")

st.title("🔍 Wyszukiwarka piłkarzy")

# Search form
col1, col2, col3 = st.columns([2, 2, 2])
with col1:
    name = st.text_input("Nazwisko", placeholder="np. Lewandowski, Szczęsny...")
with col2:
    team = st.text_input("Klub", placeholder="np. Barcelona, Juventus...")
with col3:
    league = st.text_input("Liga", placeholder="np. La Liga, Serie A...")

limit = st.slider("Maksymalna liczba wyników", 5, 100, 20)

if st.button("🔍 Szukaj", type="primary"):
    if not any([name, team, league]):
        st.warning("Wprowadź przynajmniej jedno kryterium wyszukiwania")
    else:
        with st.spinner("Wyszukuję..."):
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
                    st.success(f"Znaleziono {len(players)} piłkarzy")

                    df = pd.DataFrame(players)

                    # Display options
                    display_cols = [c for c in ["name", "position", "team", "league"] if c in df.columns]
                    st.dataframe(df[display_cols], use_container_width=True)

                    # Player details on click
                    if len(players) == 1:
                        st.json(players[0])
                else:
                    st.info("Nie znaleziono piłkarzy spełniających podane kryteria")

            except requests.RequestException as e:
                st.error(f"Błąd połączenia z API: {e}")
