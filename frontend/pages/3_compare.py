"""Compare page - player comparison (Premium feature)."""

import os

import streamlit as st
import plotly.graph_objects as go
import requests

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000/api/v1")

st.set_page_config(page_title="Porównaj", page_icon="⚖️", layout="wide")

st.title("⚖️ Porównywarka piłkarzy")

# Premium check (placeholder)
st.warning("🚧 Ta funkcja jest dostępna w wersji Premium ($9.99/mc)")

st.markdown("""
**Premium unlocks:**
- Porównywanie statystyk dwóch piłkarzy
- Radar charts
- Szczegółowe tabele porównawcze
- Export do CSV
""")

# UI Preview (non-functional)
col1, col2 = st.columns(2)

with col1:
    st.subheader("Piłkarz 1")
    st.text_input("Nazwisko", placeholder="np. Lewandowski", disabled=True)
    st.selectbox("Sezon", ["2025/26"], disabled=True)

with col2:
    st.subheader("Piłkarz 2")
    st.text_input("Nazwisko", placeholder="np. Piątek", disabled=True, key="p2_name")
    st.selectbox("Sezon", ["2025/26"], disabled=True, key="p2_season")

st.button("📊 Porównaj", disabled=True)

# Preview of what radar chart would look like
st.markdown("---")
st.subheader("Podgląd radar chart")

categories = ['Gole', 'Asysty', 'xG/90', 'xA/90', 'Minuty']
fig = go.Figure()

fig.add_trace(go.Scatterpolar(
    r=[80, 60, 75, 55, 90],
    theta=categories,
    fill='toself',
    name='Piłkarz 1'
))

fig.add_trace(go.Scatterpolar(
    r=[50, 70, 45, 65, 60],
    theta=categories,
    fill='toself',
    name='Piłkarz 2'
))

fig.update_layout(
    polar=dict(radialaxis=dict(visible=True, range=[0, 100])),
    showlegend=True,
    title="Przykładowy radar chart (dane demonstracyjne)"
)

st.plotly_chart(fig, use_container_width=True)

st.info("Odblokuj Premium, aby porównywać prawdziwych piłkarzy!")
