# frontend/utils/theme.py
"""Theme utilities for dark mode only."""

import streamlit as st
from typing import Tuple


# Dark theme colors (only theme supported)
COLORS = {
    "bg_primary": "#1a1a1a",
    "bg_secondary": "#262626",
    "bg_card": "#2d2d2d",
    "text_primary": "#ffffff",
    "text_secondary": "#b0b0b0",
    "text_muted": "#888888",
    "border_color": "#404040",
    "accent_red": "#FF6B6B",
    "accent_teal": "#4ECDC4",
}


def get_theme_css() -> str:
    """Return CSS with variables for dark theme."""
    return f"""
    <style>
    :root {{
        --bg-primary: {COLORS['bg_primary']};
        --bg-secondary: {COLORS['bg_secondary']};
        --bg-card: {COLORS['bg_card']};
        --text-primary: {COLORS['text_primary']};
        --text-secondary: {COLORS['text_secondary']};
        --text-muted: {COLORS['text_muted']};
        --border-color: {COLORS['border_color']};
        --accent-red: {COLORS['accent_red']};
        --accent-teal: {COLORS['accent_teal']};
    }}

    /* Stats Container */
    .stats-container {{
        background-color: {COLORS['bg_card']};
        border: 1px solid {COLORS['border_color']};
        border-radius: 10px;
        padding: 15px;
        margin: 5px;
        min-height: 300px;
    }}

    .stats-header {{
        color: {COLORS['text_primary']};
        font-size: 1.1rem;
        font-weight: 600;
        margin-bottom: 15px;
        padding-bottom: 10px;
        border-bottom: 1px solid {COLORS['border_color']};
    }}

    .stats-table {{
        width: 100%;
        border-collapse: collapse;
    }}

    .stats-table th {{
        color: {COLORS['text_muted']};
        font-size: 0.75rem;
        text-transform: uppercase;
        text-align: left;
        padding: 8px 5px;
        border-bottom: 1px solid {COLORS['border_color']};
    }}

    .stats-table td {{
        color: {COLORS['text_primary']};
        font-size: 1.3rem;
        font-weight: bold;
        padding: 10px 5px;
    }}

    .stats-label {{
        color: {COLORS['text_muted']};
        font-size: 0.8rem;
    }}

    .details-section {{
        margin-top: 15px;
        padding-top: 10px;
        border-top: 1px solid {COLORS['border_color']};
    }}

    .detail-row {{
        display: flex;
        justify-content: space-between;
        padding: 5px 0;
        color: {COLORS['text_secondary']};
        font-size: 0.9rem;
    }}

    .detail-value {{
        color: {COLORS['text_primary']};
        font-weight: 500;
    }}

    .subheader {{
        color: {COLORS['text_muted']};
        font-size: 0.75rem;
        margin-top: -5px;
        margin-bottom: 10px;
    }}

    /* Player Card */
    .player-card {{
        background: {COLORS['bg_card']};
        border: 1px solid {COLORS['border_color']};
        border-radius: 8px;
        padding: 1rem;
        margin: 0.5rem 0;
    }}

    .player-name {{
        color: {COLORS['text_primary']};
        font-weight: 600;
        font-size: 1rem;
    }}

    .player-info {{
        color: {COLORS['text_secondary']};
        font-size: 0.9rem;
    }}

    /* Header */
    .app-header {{
        text-align: center;
        padding: 1rem 0;
    }}

    .app-header h1 {{
        color: {COLORS['text_primary']};
        margin-bottom: 0.25rem;
    }}

    .app-header .subtitle {{
        font-size: 1.1rem;
        color: {COLORS['text_secondary']};
    }}

    /* Divider */
    .theme-divider {{
        border: none;
        border-top: 1px solid {COLORS['border_color']};
        margin: 1rem 0;
    }}

    /* Section title */
    .section-title {{
        text-align: center;
        color: {COLORS['text_primary']};
    }}
    </style>
    """


def render_header(page_title: str = "", page_icon: str = "") -> None:
    """Render consistent header across all pages."""
    title = f"{page_icon} {page_title}" if page_icon else page_title

    st.markdown(f"""
    <div class="app-header">
        <h1>🇵🇱 Polish Footballers Abroad</h1>
        <p class="subtitle">Track Polish footballers in the best leagues worldwide!</p>
    </div>
    <hr class="theme-divider">
    {f'<h2 class="section-title">{title}</h2>' if title else ''}
    """, unsafe_allow_html=True)


def apply_plotly_theme(fig):
    """Apply dark theme styling to a Plotly figure."""
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#ffffff"),
    )
    fig.update_xaxes(gridcolor="#404040", linecolor="#404040")
    fig.update_yaxes(gridcolor="#404040", linecolor="#404040")
    return fig


def get_chart_colors() -> Tuple[str, str]:
    """Get accent colors for charts."""
    return ("#FF6B6B", "#4ECDC4")
