# frontend/utils/theme.py
"""Theme utilities for dark/light mode support."""

import streamlit as st
import streamlit.components.v1 as components
from typing import Tuple


DARK_COLORS = {
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

LIGHT_COLORS = {
    "bg_primary": "#ffffff",
    "bg_secondary": "#f8f9fa",
    "bg_card": "#ffffff",
    "text_primary": "#1a1a1a",
    "text_secondary": "#4a4a4a",
    "text_muted": "#888888",
    "border_color": "#e0e0e0",
    "accent_red": "#FF6B6B",
    "accent_teal": "#4ECDC4",
}


def get_theme_css(dark_mode: bool = True) -> str:
    """Return CSS with variables for current theme."""
    colors = DARK_COLORS if dark_mode else LIGHT_COLORS

    return f"""
    <style>
    :root {{
        --bg-primary: {colors['bg_primary']};
        --bg-secondary: {colors['bg_secondary']};
        --bg-card: {colors['bg_card']};
        --text-primary: {colors['text_primary']};
        --text-secondary: {colors['text_secondary']};
        --text-muted: {colors['text_muted']};
        --border-color: {colors['border_color']};
        --accent-red: {colors['accent_red']};
        --accent-teal: {colors['accent_teal']};
    }}

    /* Stats Container */
    .stats-container {{
        background-color: var(--bg-card);
        border: 1px solid var(--border-color);
        border-radius: 10px;
        padding: 15px;
        margin: 5px;
        min-height: 300px;
    }}

    .stats-header {{
        color: var(--text-primary);
        font-size: 1.1rem;
        font-weight: 600;
        margin-bottom: 15px;
        padding-bottom: 10px;
        border-bottom: 1px solid var(--border-color);
    }}

    .stats-table {{
        width: 100%;
        border-collapse: collapse;
    }}

    .stats-table th {{
        color: var(--text-muted);
        font-size: 0.75rem;
        text-transform: uppercase;
        text-align: left;
        padding: 8px 5px;
        border-bottom: 1px solid var(--border-color);
    }}

    .stats-table td {{
        color: var(--text-primary);
        font-size: 1.3rem;
        font-weight: bold;
        padding: 10px 5px;
    }}

    .stats-label {{
        color: var(--text-muted);
        font-size: 0.8rem;
    }}

    .details-section {{
        margin-top: 15px;
        padding-top: 10px;
        border-top: 1px solid var(--border-color);
    }}

    .detail-row {{
        display: flex;
        justify-content: space-between;
        padding: 5px 0;
        color: var(--text-secondary);
        font-size: 0.9rem;
    }}

    .detail-value {{
        color: var(--text-primary);
        font-weight: 500;
    }}

    .subheader {{
        color: var(--text-muted);
        font-size: 0.75rem;
        margin-top: -5px;
        margin-bottom: 10px;
    }}

    /* Player Card */
    .player-card {{
        background: var(--bg-card);
        border: 1px solid var(--border-color);
        border-radius: 8px;
        padding: 1rem;
        margin: 0.5rem 0;
    }}

    .player-name {{
        color: var(--text-primary);
        font-weight: 600;
        font-size: 1rem;
    }}

    .player-info {{
        color: var(--text-secondary);
        font-size: 0.9rem;
    }}

    /* Header */
    .app-header {{
        text-align: center;
        padding: 1rem 0;
    }}

    .app-header h1 {{
        color: var(--text-primary);
        margin-bottom: 0.25rem;
    }}

    .app-header .subtitle {{
        font-size: 1.1rem;
        color: var(--text-secondary);
    }}

    /* Divider */
    .theme-divider {{
        border: none;
        border-top: 1px solid var(--border-color);
        margin: 1rem 0;
    }}

    /* Section title */
    .section-title {{
        text-align: center;
        color: var(--text-primary);
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


def theme_toggle(key: str = "dark_mode") -> bool:
    """Render theme toggle in sidebar. Returns True for dark mode."""
    with st.sidebar:
        # Default to True (dark mode)
        dark_mode = st.toggle(
            "🌙 Dark mode",
            value=st.session_state.get(key, True),
            key=key
        )

        # Store in session state
        st.session_state[key] = dark_mode

        # Sync to localStorage via JavaScript
        components.html(f"""
        <script>
        localStorage.setItem('streamlit_theme', '{'dark' if dark_mode else 'light'}');
        </script>
        """, height=0)

    return dark_mode


def init_theme() -> bool:
    """Initialize theme from localStorage. Returns dark_mode state."""
    # Check session state first
    if "dark_mode" in st.session_state:
        return st.session_state.dark_mode

    # Default to dark mode
    st.session_state.dark_mode = True
    return True


def apply_plotly_theme(fig, dark_mode: bool = True):
    """Apply theme-appropriate styling to a Plotly figure."""
    if dark_mode:
        fig.update_layout(
            template="plotly_dark",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#ffffff"),
        )
        # Update grid and axis colors
        fig.update_xaxes(gridcolor="#404040", linecolor="#404040")
        fig.update_yaxes(gridcolor="#404040", linecolor="#404040")
    else:
        fig.update_layout(
            template="plotly_white",
            paper_bgcolor="rgba(255,255,255,0)",
            plot_bgcolor="rgba(248,249,250,1)",
            font=dict(color="#1a1a1a"),
        )
        # Update grid and axis colors
        fig.update_xaxes(gridcolor="#e0e0e0", linecolor="#e0e0e0")
        fig.update_yaxes(gridcolor="#e0e0e0", linecolor="#e0e0e0")

    return fig


def get_chart_colors() -> Tuple[str, str]:
    """Get accent colors for charts (consistent across themes)."""
    return ("#FF6B6B", "#4ECDC4")
