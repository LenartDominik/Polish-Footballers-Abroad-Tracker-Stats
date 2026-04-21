"""Bilingual support - EN/PL translations."""

import streamlit as st

TRANSLATIONS: dict[str, dict[str, str]] = {
    "en": {
        # Header
        "app_title": "Polish Footballers Abroad",
        "app_subtitle": "Track Polish footballers in the best leagues worldwide!",

        # Sidebar
        "sidebar_title": "⚽ Polish Footballers Abroad",
        "filters": "Filters",
        "search_player": "🔍 Search Player",
        "club": "🏟️ Club",
        "all": "All",
        "select_player": "Select player:",

        # Tabs
        "tab_dashboard": "🏆 Dashboard",
        "tab_search": "🔍 Search",
        "tab_compare": "⚖️ Compare",
        "tab_zones": "📍 Position Zones",

        # Stats columns
        "league": "League",
        "league_stats": "League Stats",
        "european_cups": "European Cups",
        "afc_champions_league": "AFC Champions League",
        "domestic_cups": "Domestic Cups",
        "season_total": "Season Total",
        "club_competitions_only": "Club competitions only",

        # Stats table headers
        "games": "Games",
        "goals": "Goals",
        "assists": "Assists",
        "cs": "CS",
        "ga": "GA",

        # Details
        "details": "📋 Details",
        "starts": "Starts",
        "minutes": "Minutes",
        "rating": "Rating",
        "g_per90": "G/90",
        "a_per90": "A/90",
        "ga_per90": "G+A/90",
        "saves": "Saves",
        "save_pct": "% Obronionych Strzałów",
        "apps": "apps",

        # Goalkeeper
        "goalkeeper": "🧤 Goalkeeper",
        "goalkeeper_short": "Goalkeeper",

        # Positions
        "forward": "⚽ Forward",
        "midfielder": "⚽ Midfielder",
        "defender": "⚽ Defender",
        "unknown_position": "⚽ Unknown",

        # Heatmap position labels
        "defensive": "Defensive",
        "attacking": "Attacking",
        "midfield_zone": "Midfield",
        "right_side": "Right",
        "left_side": "Left",
        "center_side": "Center",
        "position_zones_title": "{name} - Position Zones",

        # Messages
        "use_filters": "🎯 Use filters in the sidebar to search for players",
        "no_players_found": 'No players found for "{name}"',
        "no_players_in_club": 'No Polish players found in "{club}"',
        "no_stats_available": "No stats available for season {season}",
        "no_data": "No data",
        "loading_stats": "Loading stats...",
        "searching": "Searching...",
        "searching_for": "Searching for '{name}'...",
        "loading_players_from": "Loading players from '{club}'...",
        "select_two_players": "👆 Select two players from the lists above",
        "select_filter": "👆 Select a filter above to search",
        "cannot_compare_self": "❌ Cannot compare a player with themselves. Select two different players.",
        "cannot_compare_gk_field": "❌ Cannot compare goalkeeper with field player",
        "backend_not_running": "⚠️ Backend not running! Start: `cd backend && uv run uvicorn app.main:app --reload --port 8000`",
        "premium_feature": "⭐ PREMIUM FEATURE",
        "no_field_players": "No field players available for heatmap visualization",
        "no_position_data": "📍 No position data available for **{name}** yet.",
        "sync_instruction": "Run sync to collect position data:\n```\ncd backend && uv run python sync_full.py\n```",

        # Compare tab
        "player_comparison": "⚖️ Player Comparison",
        "player_1": "Player 1",
        "player_2": "Player 2",
        "select_placeholder": "-- Select --",
        "select_stats": "Select stats",
        "compare_btn": "📊 Compare",
        "league_games_only": "📊 League games only",
        "goalkeepers_label": "🧤 Goalkeepers",
        "field_players_label": "⚽ Field Players",
        "clean_sheets": "Clean Sheets",
        "goals_against": "Goals Against",
        "penalties_saved": "Penalties Saved",
        "matches": "Matches",
        "no_data_compare": "No data",

        # Search tab
        "player_search": "🔍 Player Search",
        "name": "Name",
        "name_placeholder": "e.g. Lewandowski, Szczesny...",
        "club_placeholder": "e.g. Barcelona, Juventus...",
        "max_results": "Max results",
        "enter_criteria": "Enter at least one search criteria",
        "found_players": "Found {count} players",
        "no_players_criteria": "No players found matching criteria",
        "search_btn": "🔍 Search",
        "api_error": "API connection error: {error}",

        # Dashboard tab
        "players_in_db": "Players in DB",
        "total_goals": "Total Goals",
        "avg_xg90": "Avg xG/90",
        "total_assists": "Total Assists",
        "top_scorers": "Top 15 Scorers",
        "xg_vs_goals": "xG/90 vs Goals (min 500 minutes)",
        "top_assisters": "Top 15 Assist Providers",
        "no_data_dashboard": "No data - start backend and check API connection",

        # Position Zones tab
        "how_to_read_title": "**📊 How to read Position Zones:**",
        "red_zones_desc": "- **Red zones** = player spent most time in this area",
        "multiple_zones_desc": "- **Multiple zones** = player played different tactical roles across matches",
        "x_axis_desc": "- **X=0** = own goal | **X=1** = opponent's goal (attack direction)",
        "y_axis_desc": "- **Y=0** = right sideline | **Y=1** = left sideline",
        "fewer_matches_title": "**⚠️ Why fewer matches than expected?**",
        "fewer_matches_api": "- Only matches with **position data available** from API are shown",
        "fewer_matches_detail": "- Some matches don't have detailed lineup/position data",
        "fewer_matches_note": "- This is **not** all matches played, only matches with zone data",
        "avg_position": "Avg Position",
        "total_minutes": "Total Minutes",
        "side_breakdown": "Side Breakdown",
        "matches_with_zone": "matches with zone data",
        "and_more_matches": "*...and {count} more matches*",
        "no_position_data_available": "No position data available",
        "loading_position_data": "Loading position data...",
        "minutes_label": "Minutes",
        "select_player_label": "Select player:",

        # Stats legend
        "stats_legend": "📊 Stats Legend",
        "legend_g90": "- **G/90**: Goals per 90 minutes - allows comparing players with different minutes played.",
        "legend_a90": "- **A/90**: Assists per 90 minutes.",
        "legend_ga90": "- **G+A/90**: Goals + Assists per 90 minutes.",
        "legend_cs": "- **CS (Goalkeepers)**: Clean Sheets - matches without conceding a goal.",
        "legend_ga": "- **GA (Goalkeepers)**: Goals Against - goals conceded.",
        "legend_save_pct": "- **Save% (Goalkeepers)**: Percentage of shots saved.",
        "legend_rating": "- **Rating**: Average match rating (1-10).",

        # Language selector label
        "language": "🌐 Language",
    },
    "pl": {
        # Header
        "app_title": "Polscy Piłkarze za Granicą",
        "app_subtitle": "Śledź polskich piłkarzy w najlepszych ligach świata!",

        # Sidebar
        "sidebar_title": "⚽ Polscy Piłkarze za Granicą",
        "filters": "Filtry",
        "search_player": "🔍 Szukaj Zawodnika",
        "club": "🏟️ Klub",
        "all": "Wszyscy",
        "select_player": "Wybierz zawodnika:",

        # Tabs
        "tab_dashboard": "🏆 Pulpit",
        "tab_search": "🔍 Szukaj",
        "tab_compare": "⚖️ Porównaj",
        "tab_zones": "📍 Strefy Pozycyjne",

        # Stats columns
        "league": "Liga",
        "league_stats": "Statystyki Ligowe",
        "european_cups": "Puchary Europejskie",
        "afc_champions_league": "Liga Mistrzów AFC",
        "domestic_cups": "Puchary Krajowe",
        "season_total": "Łączna Suma w Sezonie",
        "club_competitions_only": "Tylko rozgrywki klubowe",

        # Stats table headers
        "games": "Mecze",
        "goals": "Gole",
        "assists": "Asysty",
        "cs": "CS",
        "ga": "GA",

        # Details
        "details": "📋 Szczegóły",
        "starts": "Występy od początku",
        "minutes": "Minuty",
        "rating": "Ocena",
        "g_per90": "G/90",
        "a_per90": "A/90",
        "ga_per90": "G+A/90",
        "saves": "Obrony",
        "save_pct": "% Obronionych Strzałów",
        "apps": "wyst.",

        # Goalkeeper
        "goalkeeper": "🧤 Bramkarz",
        "goalkeeper_short": "Bramkarz",

        # Positions
        "forward": "⚽ Napastnik",
        "midfielder": "⚽ Pomocnik",
        "defender": "⚽ Obrońca",
        "unknown_position": "⚽ Nieznana",

        # Heatmap position labels
        "defensive": "Defensywna",
        "attacking": "Atakująca",
        "midfield_zone": "Środek Pola",
        "right_side": "Prawa",
        "left_side": "Lewa",
        "center_side": "Środek",
        "position_zones_title": "{name} - Strefy Pozycyjne",

        # Messages
        "use_filters": "🎯 Użyj filtrów w panelu bocznym, aby wyszukać zawodników",
        "no_players_found": 'Nie znaleziono zawodników dla "{name}"',
        "no_players_in_club": 'Nie znaleziono polskich zawodników w "{club}"',
        "no_stats_available": "Brak dostępnych statystyk dla sezonu {season}",
        "no_data": "Brak danych",
        "loading_stats": "Ładowanie statystyk...",
        "searching": "Wyszukiwanie...",
        "searching_for": "Wyszukiwanie '{name}'...",
        "loading_players_from": "Ładowanie zawodników z '{club}'...",
        "select_two_players": "👆 Wybierz dwóch zawodników z list powyżej",
        "select_filter": "👆 Wybierz filtr powyżej, aby wyszukać",
        "cannot_compare_self": "❌ Nie można porównać zawodnika z samym sobą. Wybierz dwóch różnych zawodników.",
        "cannot_compare_gk_field": "❌ Nie można porównać bramkarza z zawodnikiem z pola",
        "backend_not_running": "⚠️ Backend nie działa! Uruchom: `cd backend && uv run uvicorn app.main:app --reload --port 8000`",
        "premium_feature": "⭐ FUNKCJA PREMIUM",
        "no_field_players": "Brak zawodników z pola do wizualizacji heatmapy",
        "no_position_data": "📍 Brak danych pozycyjnych dla **{name}**.",
        "sync_instruction": "Uruchom sync aby zebrać dane pozycyjne:\n```\ncd backend && uv run python sync_full.py\n```",

        # Compare tab
        "player_comparison": "⚖️ Porównanie Zawodników",
        "player_1": "Zawodnik 1",
        "player_2": "Zawodnik 2",
        "select_placeholder": "-- Wybierz --",
        "select_stats": "Wybierz statystyki",
        "compare_btn": "📊 Porównaj",
        "league_games_only": "📊 Tylko mecze ligowe",
        "goalkeepers_label": "🧤 Bramkarze",
        "field_players_label": "⚽ Zawodnicy z Pola",
        "clean_sheets": "Czyste Konta",
        "goals_against": "Stracone Gole",
        "penalties_saved": "Obronione Rzuty Karne",
        "matches": "Mecze",
        "no_data_compare": "Brak danych",

        # Search tab
        "player_search": "🔍 Szukaj Zawodników",
        "name": "Imię/Nazwisko",
        "name_placeholder": "np. Lewandowski, Szczęsny...",
        "club_placeholder": "np. Barcelona, Juventus...",
        "max_results": "Maks. wyników",
        "enter_criteria": "Wpisz przynajmniej jedno kryterium wyszukiwania",
        "found_players": "Znaleziono {count} zawodników",
        "no_players_criteria": "Nie znaleziono zawodników spełniających kryteria",
        "search_btn": "🔍 Szukaj",
        "api_error": "Błąd połączenia z API: {error}",

        # Dashboard tab
        "players_in_db": "Zawodnicy w bazie",
        "total_goals": "Łącznie Goli",
        "avg_xg90": "Średnie xG/90",
        "total_assists": "Łącznie Asyst",
        "top_scorers": "Top 15 Strzelców",
        "xg_vs_goals": "xG/90 vs Gole (min 500 minut)",
        "top_assisters": "Top 15 Asystentów",
        "no_data_dashboard": "Brak danych - uruchom backend i sprawdź połączenie z API",

        # Position Zones tab
        "how_to_read_title": "**📊 Jak czytać Strefy Pozycyjne:**",
        "red_zones_desc": "- **Czerwone strefy** = gracz spędził najwięcej czasu w tym obszarze",
        "multiple_zones_desc": "- **Wiele stref** = gracz grał w różnych rolach taktycznych w meczach",
        "x_axis_desc": "- **X=0** = własna bramka | **X=1** = bramka przeciwnika (kierunek ataku)",
        "y_axis_desc": "- **Y=0** = prawa linia boczna | **Y=1** = lewa linia boczna",
        "fewer_matches_title": "**⚠️ Dlaczego mniej meczów niż oczekiwano?**",
        "fewer_matches_api": "- Tylko mecze z **dostępnymi danymi pozycyjnymi** z API są pokazane",
        "fewer_matches_detail": "- Niektóre mecze nie mają szczegółowych danych o składzie/pozycji",
        "fewer_matches_note": "- To **nie są** wszystkie rozegrane mecze, tylko mecze z danymi strefowymi",
        "avg_position": "Średnia Pozycja",
        "total_minutes": "Łącznie Minut",
        "side_breakdown": "Rozkład Stron",
        "matches_with_zone": "mecze z danymi strefowymi",
        "and_more_matches": "*...i {count} kolejnych meczów*",
        "no_position_data_available": "Brak danych pozycyjnych",
        "loading_position_data": "Ładowanie danych pozycyjnych...",
        "minutes_label": "Minuty",
        "select_player_label": "Wybierz zawodnika:",

        # Stats legend
        "stats_legend": "📊 Legenda Statystyk",
        "legend_g90": "- **G/90**: Gole na 90 minut - pozwala porównać zawodników z różną liczbą rozegranych minut.",
        "legend_a90": "- **A/90**: Asysty na 90 minut.",
        "legend_ga90": "- **G+A/90**: Gole + Asysty na 90 minut.",
        "legend_cs": "- **CS (Bramkarze)**: Czyste Konta - mecze bez straconego gola.",
        "legend_ga": "- **GA (Bramkarze)**: Stracone Gole.",
        "legend_save_pct": "- **% Obronionych Strzałów (Bramkarze)**: Procent obronionych strzałów.",
        "legend_rating": "- **Ocena**: Średnia ocena meczu (1-10).",

        # Language selector label
        "language": "🌐 Język",
    },
}


def t(key: str, **kwargs) -> str:
    """Return translated text for current language. Supports format kwargs like {name}."""
    lang = st.session_state.get("lang", "pl")
    text = TRANSLATIONS.get(lang, {}).get(key, key)
    if kwargs:
        text = text.format(**kwargs)
    return text


def language_selector():
    """Render language selectbox in sidebar. Call at top of every page."""
    lang_options = ["pl", "en"]
    format_map = {"pl": "🇵🇱 Polski", "en": "🇺🇸 English"}
    current = st.session_state.get("lang", "pl")

    st.sidebar.selectbox(
        "🌐 Language",
        options=lang_options,
        index=lang_options.index(current),
        format_func=lambda x: format_map.get(x, x),
        key="lang",
    )


def get_position_display(position: str | None) -> str:
    """Return position with emoji, translated."""
    if position == "GK":
        return t("goalkeeper")
    elif position in ["F", "FW", "Forward", "ST", "CF"]:
        return t("forward")
    elif position in ["M", "MF", "Midfielder"]:
        return t("midfielder")
    elif position in ["D", "DF", "Defender"]:
        return t("defender")
    elif position:
        return f"⚽ {position}"
    else:
        return t("unknown_position")


def clean_team_name(team: str | None) -> str:
    """Clean team name - remove duplicate player name if present."""
    if not team:
        return "N/A"
    if " - " in team:
        return team.split(" - ", 1)[1]
    return team
