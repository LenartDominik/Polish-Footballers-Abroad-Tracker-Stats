# -*- coding: utf-8 -*-
"""Sync: Polish players with minutes from lineups. Supports incremental and full sync."""

from __future__ import annotations

import argparse
import asyncio
import sys
import os
from datetime import datetime, timedelta
from collections import defaultdict
# position is tracked via POLISH_PLAYERS dict
from typing import Any, TypedDict


class PlayerMatchStats(TypedDict):
    """Stats dict for accumulating player stats during sync."""
    minutes: int
    goals: int
    assists: int
    yellow_cards: int
    red_cards: int
    matches_total: int
    matches_started: int
    matches_subbed: int
    ratings: list[float]
    clean_sheets: int
    saves: int
    goals_against: int
    shots_on_target_against: int


def _make_player_stats() -> PlayerMatchStats:
    """Factory function for default player stats."""
    return {
        "minutes": 0, "goals": 0, "assists": 0,
        "yellow_cards": 0, "red_cards": 0,
        "matches_total": 0, "matches_started": 0, "matches_subbed": 0,
        "ratings": [],
        "clean_sheets": 0, "saves": 0, "goals_against": 0,
        "shots_on_target_against": 0,
    }


# Fix Windows encoding issues
if sys.platform == "win32":
    if sys.stdout:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[misc]
    if sys.stderr:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[misc]

os.environ['PYTHONIOENCODING'] = 'utf-8'

import httpx
from dotenv import load_dotenv
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

load_dotenv()

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.db.models import Player, PlayerStats, PlayerStatsByCompetition, SyncState, SyncedMatch, PlayerHeatmapPosition
from app.services.rapidapi import calculate_per_90
from app.services.rate_limiter import RateLimiter, InMemoryRateLimiter, MAX_REQUESTS_PER_MINUTE, MAX_REQUESTS_PER_HOUR, MAX_REQUESTS_PER_MONTH

# Configuration
API_HOST = "free-api-live-football-data.p.rapidapi.com"
API_KEY = settings.rapidapi_key

# Polish player IDs to track: {rapidapi_id: {"name": str, "position": str}}
# Positions: GK (bramkarz), DF (obrońca), MF (pomocnik), FW (napastnik)
POLISH_PLAYERS = {
    93447: {"name": "Robert Lewandowski", "position": "FW"},
    169718: {"name": "Wojciech Szczęsny", "position": "GK"},
    543298: {"name": "Krzysztof Piątek", "position": "FW"},
    362212: {"name": "Piotr Zieliński", "position": "MF"},
    1647807: {"name": "Oskar Pietuszewski", "position": "FW"},
    490868: {"name": "Jan Bednarek", "position": "DF"},
    1021834: {"name": "Jakub Kiwior", "position": "DF"},
    760722: {"name": "Kamil Grabara", "position": "GK"},
    908847: {"name": "Mateusz Żukowski", "position": "FW"},
    630036: {"name": "Mateusz Lis", "position": "GK"},
    954194: {"name": "Mateusz Bogusz", "position": "MF"},
    742332: {"name": "Bartosz Slisz", "position": "MF"},
    1051411: {"name": "Kacper Kozłowski", "position": "MF"},
    1053714: {"name": "Nicola Zalewski", "position": "MF"},
    1511063: {"name": "Jan Ziółkowski", "position": "DF"},
    557396: {"name": "Adam Buksa", "position": "FW"},
    1067260: {"name": "Jakub Kamiński", "position": "MF"},
    1800401: {"name": "Kacper Potulski", "position": "DF"},
    361712: {"name": "Adam Dźwigała", "position": "DF"},
    1112702: {"name": "Arkadiusz Pyrka", "position": "MF"},
    502543: {"name": "Dawid Kownacki", "position": "FW"},
    1053713: {"name": "Maik Nawrocki", "position": "DF"},
    1065940: {"name": "Michał Karbownik", "position": "DF"},
    1355526: {"name": "Maxi Oyedele", "position": "MF"},
    402419: {"name": "Przemysław Frankowski", "position": "MF"},
    765466: {"name": "Sebastian Szymański", "position": "MF"},
    891855: {"name": "Jakub Moder", "position": "MF"},
    560109: {"name": "Oskar Zawada", "position": "FW"},
    1116778: {"name": "Szymon Włodarczyk", "position": "FW"},
    277460: {"name": "Arkadiusz Milik", "position": "FW"},
    689987: {"name": "Jakub Piotrowski", "position": "MF"},
    1096327: {"name": "Jakub Stolarczyk", "position": "GK"},
    1131992: {"name": "Jakub Kałuziński", "position": "MF"},
    488960: {"name": "Michał Helik", "position": "DF"},
    862717: {"name": "Przemysław Płacheta", "position": "MF"},
    178732: {"name": "Łukasz Skorupski", "position": "GK"},
    556952: {"name": "Krystian Bielik", "position": "DF"},
    198099: {"name": "Bartosz Bereszyński", "position": "DF"},
    920861: {"name": "Adrian Benedyczak", "position": "FW"},
    1154332: {"name": "Mateusz Kochalski", "position": "GK"},
    823121: {"name": "Tymoteusz Puchacz", "position": "DF"},
    1380468: {"name": "Jan Faberski", "position": "MF"},
    943056: {"name": "Daniel Bielica", "position": "GK"},
    306174: {"name": "Tomasz Kędziora", "position": "DF"},
    361403: {"name": "Karol Linetty", "position": "MF"},
    724909: {"name": "Radosław Majecki", "position": "GK"},
    815981: {"name": "Konrad Michalak", "position": "FW"},
    943059: {"name": "Cezary Miszta", "position": "GK"},
    1484822: {"name": "Filip Rózga", "position": "MF"},
    962113: {"name": "Łukasz Poręba", "position": "MF"},
    1245669: {"name": "Patryk Peda", "position": "DF"},
    1276988: {"name": "Dariusz Stalmach", "position": "MF"},
    954190: {"name": "Michał Skóraś", "position": "MF"},
    860592: {"name": "Sebastian Walukiewicz", "position": "DF"},
    555646: {"name": "Mateusz Wieteska", "position": "DF"},
    729731: {"name": "Matty Cash", "position": "DF"},
    1229761: {"name": "Mateusz Łęgowski", "position": "MF"},
    558136: {"name": "Karol Świderski", "position": "FW"},
    1070709: {"name": "Filip Szymczak", "position": "FW"},
    1116774: {"name": "Łukasz Łakomy", "position": "MF"},
}

# Teams to sync with multiple competitions
TEAMS = {
    8634: {
        "name": "FC Barcelona",
        "competitions": [
            {"name": "La Liga", "league_id": 87},
            {"name": "Copa del Rey", "league_id": 138},
            {"name": "Supercopa", "league_id": 139},
            {"name": "Champions League", "league_id": 42},
        ],
    },
    203826: {
        "name": "Al-Duhail SC",
        "competitions": [
            {"name": "Qatar Stars League", "league_id": 535},
            {"name": "QSL Cup", "league_id": 11017},
            {"name": "AFC Champions League Elite", "league_id": 525},
            {"name": "Amir of Qatar Cup", "league_id": 11018},
            {"name": "Qatar Cup", "league_id": 11016},
        ],
    },
    8636: {
        "name": "Inter",
        "competitions": [
            {"name": "Serie A", "league_id": 55},
            {"name": "Coppa Italia", "league_id": 141},
            {"name": "Champions League", "league_id": 42},
            {"name": "Supercoppa", "league_id": 222},
        ],
    },
    9773: {
        "name": "FC Porto",
        "competitions": [
            {"name": "Primeira Liga", "league_id": 61},
            {"name": "Taça de Portugal", "league_id": 186},
            {"name": "Taça da Liga", "league_id": 97},
            {"name": "Supertaça", "league_id": 532},
            {"name": "Champions League", "league_id": 42},
            {"name": "Europa League", "league_id": 73},
            {"name": "Europa League Qualification", "league_id": 10613},
        ],
    },
    8721: {
        "name": "VfL Wolfsburg",
        "competitions": [
            {"name": "Bundesliga", "league_id": 54},
            {"name": "DFB-Pokal", "league_id": 209},
        ],
    },
    8188: {
        "name": "1. FC Magdeburg",
        "competitions": [
            {"name": "2. Bundesliga", "league_id": 146},
            {"name": "DFB-Pokal", "league_id": 209},
        ],
    },
    1925:{
        "name": "Göztepe",
        "competitions": [
            {"name": "Super Lig", "league_id": 71},
            {"name": "Turkish Cup", "league_id": 151},
        ],
    },
    8259: {
        "name": "Houston Dynamo FC",
        "competitions": [
            {"name": "MLS", "league_id": 130},
            {"name": "US Open Cup", "league_id": 9441},
        ],
},
    8595: {
        "name": "Brøndby IF",
        "competitions": [
            {"name": "Superligaen", "league_id": 46},
            {"name": "DBU Pokalen", "league_id": 10046},
        ],
},  
    4081: {
        "name": "Gaziantep FK",
        "competitions": [
            {"name": "Süper Lig", "league_id": 71},
            {"name": "Turkish Cup", "league_id": 151},
        ],
},
    8524: {
        "name": "Atalanta Bergamo",
        "competitions": [
            {"name": "Serie A", "league_id": 55},
            {"name": "Coppa Italia", "league_id": 141},
            {"name": "Champions League", "league_id": 42},
        ]
    },
    8686: {
        "name": "AS Roma",
        "competitions": [
            {"name": "Serie A", "league_id": 55},
            {"name": "Coppa Italia", "league_id": 141},
            {"name": "Europa League", "league_id": 73},
        ]
},
    8600: {
        "name": "Udinese",
        "competitions": [
            {"name": "Serie A", "league_id": 55},
            {"name": "Coppa Italia", "league_id": 141},
        ]
    },
    8722: {
        "name": "1. FC Köln",
        "competitions": [
            {"name": "Bundesliga", "league_id": 54},
            {"name": "DFB-Pokal", "league_id": 209},
        ],
    },
    9905: {
        "name": "Mainz 05",
        "competitions": [
            {"name": "Bundesliga", "league_id": 54},
            {"name": "DFB-Pokal", "league_id": 209},
            {"name": "Conference League", "league_id": 10216},
        ],

},
    8152: {
        "name": "St. Pauli",
        "competitions": [
            {"name": "Bundesliga", "league_id": 54},
            {"name": "DFB-Pokal", "league_id": 209},
        ],
    },
    8177: {
        "name": "Hertha BSC",
        "competitions": [
            {"name": "2. Bundesliga", "league_id": 146},
            {"name": "DFB-Pokal", "league_id": 209},
        ],
    },
    9904: {
        "name": "Hannover 96",
        "competitions": [
            {"name": "2. Bundesliga", "league_id": 146},
            {"name": "DFB-Pokal", "league_id": 209},
        ],
    },
    9848: {
        "name": "Strasbourg",
        "competitions": [
            {"name": "Ligue 1", "league_id": 53},
            {"name": "Coupe de France", "league_id": 134},
            {"name": "Conference League", "league_id": 10216},
        ],
    },
    9851: {
        "name": "Rennes",
        "competitions": [
            {"name": "Ligue 1", "league_id": 53},
            {"name": "Coupe de France", "league_id": 134},
        ],
},
    10235: {
        "name": "Feyenoord",
        "competitions": [
            {"name": "Eredivisie", "league_id": 57},
            {"name": "KNVB Cup", "league_id": 235},
            {"name": "Europa League", "league_id": 73},
        ],
},
    8674: {
        "name": "FC Groningen",
        "competitions": [
            {"name": "Eredivisie", "league_id": 57},
            {"name": "KNVB Cup", "league_id": 235},
        ],
},
    10218: {
        "name": "Excelsior",
        "competitions": [
            {"name": "Eredivisie", "league_id": 57},
            {"name": "KNVB Cup", "league_id": 235}, 
        ],
    },
    9885:
    {
        "name": "Juventus",
        "competitions": [
            {"name": "Serie A", "league_id": 55},
            {"name": "Coppa Italia", "league_id": 141},
            {"name": "Champions League", "league_id": 42},
        ],
    },
    8197: {
        "name": "Leicester City",
        "competitions": [
            {"name": "Championship", "league_id": 48},
            {"name": "FA Cup", "league_id": 132},
            {"name": "EFL Cup", "league_id": 133},
        ],  
},
    1933: {
        "name": "Başakşehir",
        "competitions": [
            {"name": "Süper Lig", "league_id": 71},
            {"name": "Turkish Cup", "league_id": 151},
        ],
    },
    8653: {
        "name": "Oxford United",
        "competitions": [
            {"name": "Championship", "league_id": 48},
            {"name": "FA Cup", "league_id": 132},
            {"name": "EFL Cup", "league_id": 133},
        ],
},
    9857: {
        "name": "Bologna",
        "competitions": [
            {"name": "Serie A", "league_id": 55},
            {"name": "Coppa Italia", "league_id": 141},
            {"name": "Europa League", "league_id": 73},
        ],

},
    8659: {
        "name": "West Bromwich Albion",
        "competitions": [
            {"name": "Championship", "league_id": 48},
            {"name": "FA Cup", "league_id": 132},
            {"name": "EFL Cup", "league_id": 133},
        ],
    },
    8540: {
        "name": "Palermo",
        "competitions": [
            {"name": "Serie B", "league_id": 86},
            {"name": "Coppa Italia", "league_id": 141},
        ],
    },
    4685: {
        "name": "Kasimpaşa",
        "competitions": [
            {"name": "Süper Lig", "league_id": 71},
            {"name": "Turkish Cup", "league_id": 151},
        ],
    },
    6413: {
        "name": "PEC Zwolle",
        "competitions": [
            {"name": "Eredivisie", "league_id": 57},
            {"name": "KNVB Cup", "league_id": 235},
        ],
    },
    9761: {
        "name": "NAC Breda",
        "competitions": [
            {"name": "Eredivisie", "league_id": 57},
            {"name": "KNVB Cup", "league_id": 235},
        ],
    },
    8619: {
        "name": "PAOK Thessaloniki",
        "competitions": [
            {"name": "Super League 1", "league_id": 135},
            {"name": "Greek Cup", "league_id": 145},
            {"name": "Europa League", "league_id": 73},
            {"name": "Europa League Qualification", "league_id": 10613},
        ],
    },
    1569: {
        "name": "Kocaelispor",
        "competitions": [
            {"name": "Süper Lig", "league_id": 71},
            {"name": "Turkish Cup", "league_id": 151},
        ],
    },
    8521: {
        "name": "Brest",
        "competitions": [
            {"name": "Ligue 1", "league_id": 53},
            {"name": "Coupe de France", "league_id": 134},
        ],
    },
    162386: {
        "name": "Panetolikos",
        "competitions": [
            {"name": "Super League 1", "league_id": 135},
            {"name": "Greek Cup", "league_id": 145},
        ],
    },
    7841 : {
        "name": "Rio Ave",
        "competitions": [
            {"name": "Primeira Liga", "league_id": 61},
            {"name": "Taça de Portugal", "league_id": 186},
        ],
    },
    10014: {
        "name": "Sturm Graz",
        "competitions": [
            {"name": "Bundesliga", "league_id": 38},
            {"name": "Austrian Cup", "league_id": 278},
            {"name": "Europa League", "league_id": 73},
            {"name": "Europa League Qualification", "league_id": 10613},
        ],
},
    8232: {
        "name": "Elversberg",
        "competitions": [
            {"name": "2. Bundesliga", "league_id": 146},
            {"name": "DFB-Pokal", "league_id": 209},
        ],
    },
    9991: {
        "name": "Gent",
        "competitions": [
            {"name": "First Division A", "league_id": 40},
            {"name": "Belgian Cup", "league_id": 149},
        ],
    },
    7943: {
        "name": "Sassuolo",
        "competitions": [
            {"name": "Serie A", "league_id": 55},
            {"name": "Coppa Italia", "league_id": 141},
        ]
    },
    10252: {
        "name": "Aston Villa",
        "competitions": [
            {"name": "Premier League", "league_id": 47},
            {"name": "FA Cup", "league_id": 132},
            {"name": "EFL Cup", "league_id": 133},
            {"name": "Europa League", "league_id": 73},
        ],
},
    4681: {
        "name": "Eyüpspor",
        "competitions": [
            {"name": "Süper Lig", "league_id": 71},
            {"name": "Turkish Cup", "league_id": 151},
        ],
},
    10200: {    
        "name": "Panathinaikos",
        "competitions": [
            {"name": "Super League 1", "league_id": 135},
            {"name": "Greek Cup", "league_id": 145},
            {"name": "Europa League", "league_id": 73},
            {"name": "Europa League Qualification", "league_id": 10613},
            {"name": "Champions League", "league_id": 42},
            {"name": "Champions League Qualification", "league_id": 10611},
        ],
},
    9986: {
        "name": "Sporting Charleroi",
        "competitions": [
            {"name": "First Division A", "league_id": 40},
            {"name": "Belgian Cup", "league_id": 149},
        ],
    },
    1773: {
        "name": "OH Leuven",
        "competitions": [
            {"name": "First Division A", "league_id": 40},
            {"name": "Belgian Cup", "league_id": 149},
        ],
    },
}






CURRENT_SEASON = "2025/26"
CACHE_TTL_HOURS = 24
SYNC_INTERVAL_HOURS = 12  # Minimum time between syncs
API_RETRY_ATTEMPTS = 3  # Retry failed API responses
API_RETRY_BASE_DELAY = 5  # Base seconds between retries (exponential: 5, 15, 45)


class APIResponseError(Exception):
    """Raised when RapidAPI returns status:'failed' in response body."""
    pass


def _check_api_status(data: dict[str, Any]) -> dict[str, Any]:
    """Check if API response body has status:'failed'. Raise APIResponseError if so."""
    status = data.get("status")
    if isinstance(status, str) and status.lower() == "failed":
        msg = data.get("message", "Unknown API error")
        raise APIResponseError(f"API error: {msg}")
    return data

# ── League tier classification ──────────────────────────────────────────
# Top ligi: angielska, niemiecka, francuska, włoska, hiszpańska,
#           portugalska, holenderska, belgijska, turecka, grecka + ich pucharki
TOP_LEAGUE_IDS = {
    47,    # Premier League
    54,    # Bundesliga
    53,    # Ligue 1
    55,    # Serie A
    87,    # La Liga
    61,    # Primeira Liga
    57,    # Eredivisie
    40,    # Belgian First Division A
    71,    # Süper Lig
    135,   # Super League 1 (Greece)
    # Domestic cups for top leagues
    138,   # Copa del Rey
    139,   # Supercopa (Spain)
    222,   # Supercoppa (Italy)
    141,   # Coppa Italia
    132,   # FA Cup
    133,   # EFL Cup
    134,   # Coupe de France
    149,   # Belgian Cup
    151,   # Turkish Cup
    186,   # Taça de Portugal
    235,   # KNVB Cup
    97,    # Taça da Liga
    532,   # Supertaça (Portugal)
    209,   # DFB-Pokal
    145,   # Greek Cup
}

# European cups: CL, EL, Conference League + qualifications
EUROPEAN_CUP_IDS = {
    42,      # Champions League
    73,      # Europa League
    10216,   # Conference League
    10611,   # Champions League Qualification
    10613,   # Europa League Qualification
}

# Niszowe ligi: reszta (duńska, MLS, 2. Bundesliga, etc.)
NICHE_LEAGUE_IDS = {
    46,      # Superligaen (Denmark)
    535,     # Qatar Stars League
    11016,   # Qatar Cup
    11017,   # QSL Cup
    11018,   # Amir of Qatar Cup
    525,     # AFC Champions League Elite
    38,      # Austrian Bundesliga
    278,     # Austrian Cup
    146,     # 2. Bundesliga
    48,      # Championship
    86,      # Serie B
    130,     # MLS
    9441,    # US Open Cup
    10046,   # DBU Pokalen (Denmark)
}


def get_tier_for_league(league_id: int) -> str:
    """Return tier name for a given league_id."""
    if league_id in EUROPEAN_CUP_IDS:
        return "european"
    if league_id in TOP_LEAGUE_IDS:
        return "top"
    if league_id in NICHE_LEAGUE_IDS:
        return "niche"
    return "niche"  # default: treat unknown as niche


# Competition type mapping
def map_competition_type(competition_name: str) -> str:
    """Map competition name to type (league, european, continental, domestic)."""
    name_lower = competition_name.lower()

    # AFC Champions League (Asian) - separate from European
    if "afc champions" in name_lower:
        return "continental"

    # European competitions (Champions League, Europa League, Conference League)
    if any(x in name_lower for x in ["champions league", "europa league", "conference league"]):
        return "european"

    # Domestic cups (national cups, supercups)
    # Note: "cup" is a common suffix for domestic cups
    if any(x in name_lower for x in ["copa del rey", "supercopa", "coppa italia", "copa", "taça", "taca", "qsl", "amir", "dfb-pokal", "pokal"]):
        return "domestic"
    # Also match "cup" but NOT "league cup" variations that are actually leagues
    if "cup" in name_lower and "league" not in name_lower and "stars" not in name_lower:
        return "domestic"

    # Default: league (national league competitions)
    return "league"


# CLI Arguments
def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Sync Polish players stats")
    parser.add_argument("--full", action="store_true", help="Full sync (all matches, ignore cache)")
    parser.add_argument("--dry-run", action="store_true", help="Preview without saving to database")
    parser.add_argument("--player", type=int, help="Sync only specific player by rapidapi_id (e.g., 1647807 for Pietuszewski)")
    parser.add_argument("--force", action="store_true", help="Force sync, ignore cache timing")
    parser.add_argument("--gk-only", action="store_true", help="Sync only goalkeepers")
    parser.add_argument("--tier", choices=["all", "top", "european", "niche"],
                        default="all", help="Sync only specific tier of competitions")
    return parser.parse_args()


# Map player_id to team_id for --player option
PLAYER_TEAMS = {
    93447: 8634,    # Lewandowski -> Barcelona
    169718: 8634,   # Szczęsny -> Barcelona
    543298: 203826, # Piątek -> Al-Duhail
    362212: 8636,   # Zieliński -> Inter
    1647807: 9773,  # Pietuszewski -> Porto
    490868: 9773,   # Bednarek -> Porto
    1021834: 9773,  # Kiwior -> Porto
    760722: 8721,   # Grabara -> Wolfsburg
    908847: 8188,   # Żukowski -> Magdeburg
    630036: 1925,   # Lis -> Göztepe
    954194: 8259,   #Bogusz - Houston Dynamo FC
    742332: 8595,   #Slisz - Brøndby IF
    1051411: 4081,  # Kacper Kozłowski - Gaziantep FK
    1053714: 8524,  # Nicola Zalewski - Atalanta Bergamo
    1511063: 8686, # Jan Ziółkowski - AS Roma
    557396: 8600,  # Adam Buksa - Udinese
    1067260: 8722, # Jakub Kamiński - 1. FC Köln
    1800401: 9905, # Kacper Potulski - Mainz 05
    361712: 8152,  # Adam Dźwigała - St. Pauli
    1112702: 8152, # Arkadiusz Pyrka - St. Pauli
    502543: 8177,  # Dawid Kownacki - Hertha BSC
    1053713: 9904, # Maik Nawrocki - Hannover 96
    1065940: 8177, # Michał Karbownik - Hertha BSC
    1355526: 9848, # Maxi Oyedele - Strasbourg
    402419: 9851,  # Przemysław Frankowski - Rennes
    765466: 9851,  # Sebastian Szymański - Rennes
    891855: 10235, # Jakub Moder - Feyenoord
    560109: 8674,  # Oskar Zawada - FC Groningen
    1116778: 10218, # Szymon Włodarczyk - Excelsior
    277460: 9885,  # Arkadiusz Milik - Juventus
    689987: 8600,  # Jakub Piotrowski - Udinese
    1096327: 8197, # Jakub Stolarczyk - Leicester City
    1131992: 1933, # Jakub Kałuziński - Başakşehir
    488960: 8653,  # Michał Helik - Oxford United
    862717: 8653,  # Przemysław Płacheta - Oxford United
    178732: 9857,  # Łukasz Skorupski - Bologna
    556952: 8659,  # Krystian Bielik - West Bromwich Albion
    198099: 8540,  # Bartosz Bereszyński - Palermo
    920861: 4685,  # Adrian Benedyczak - Kasımpaşa
    1380468: 6413, # Jan Faberski - PEC Zwolle
    943056: 9761,  # Daniel Bielica - NAC Breda
    306174: 8619,  # Tomasz Kędziora - PAOK Thessaloniki
    361403: 1569,  # Karol Linetty - Kocaelispor
    724909: 8521,  # Radosław Majecki - Brest
    815981: 162386, # Konrad Michalak - Panetolikos
    943059: 7841,  # Cezary Miszta - Rio Ave
    1484822: 10014, # Filip Rózga - Sturm Graz
    962113: 8232,  # Łukasz Poręba - Elversberg
    1245669: 8540, # Patryk Peda - Palermo
    1276988: 8188, # Dariusz Stalmach - Magdeburg    
    954190: 9991,  # Michał Skóraś - Gent
    860592: 7943,  # Sebastian Walukiewicz - Sassuolo
    555646: 1569,  # Mateusz Wieteska - Kocaelispor
    729731: 10252, # Matty Cash - Aston Villa
    1229761: 4681, # Mateusz Łęgowski - Eyüpspor
    558136: 10200, # Karol Świderski - Panathinaikos
    1070709: 9986, # Filip Szymczak - Sporting Charleroi
    1116774: 1773, # Łukasz Łakomy - OH Leuven
}


# Sync state helpers
async def get_sync_state(session, team_id: int, competition_id: int) -> SyncState | None:
    """Get sync state for a team/competition combination."""
    result = await session.execute(
        select(SyncState).where(
            SyncState.team_id == team_id,
            SyncState.competition_id == competition_id,
            SyncState.season == CURRENT_SEASON,
        )
    )
    return result.scalar_one_or_none()


async def update_sync_state(session, team_id: int, team_name: str, competition_id: int,
                            competition_name: str, last_match_id: int, matches_synced: int):
    """Update or create sync state after processing matches."""
    sync_state = await get_sync_state(session, team_id, competition_id)

    if sync_state:
        sync_state.last_sync_at = datetime.utcnow()
        sync_state.last_match_id = last_match_id
        sync_state.matches_synced += matches_synced
        sync_state.next_sync_at = datetime.utcnow() + timedelta(hours=SYNC_INTERVAL_HOURS)
    else:
        sync_state = SyncState(
            team_id=team_id,
            team_name=team_name,
            competition_id=competition_id,
            competition_name=competition_name,
            season=CURRENT_SEASON,
            last_sync_at=datetime.utcnow(),
            last_match_id=last_match_id,
            matches_synced=matches_synced,
            next_sync_at=datetime.utcnow() + timedelta(hours=SYNC_INTERVAL_HOURS),
        )
        session.add(sync_state)


async def is_match_synced(session, match_id: int, team_id: int) -> bool:
    """Check if a match has already been synced (deduplication)."""
    result = await session.execute(
        select(SyncedMatch).where(
            SyncedMatch.match_id == match_id,
            SyncedMatch.team_id == team_id,
        )
    )
    return result.scalar_one_or_none() is not None


async def mark_match_synced(session, match_id: int, team_id: int, competition_id: int):
    """Mark a match as synced to prevent duplicate processing."""
    stmt = insert(SyncedMatch).values(
        match_id=match_id,
        team_id=team_id,
        competition_id=competition_id,
    ).on_conflict_do_nothing(constraint="uq_match_team")
    await session.execute(stmt)


async def sync_team_v2(team_id: int, team_info: dict, session, args, player_filter: list[int] | None = None) -> int:
    """Sync Polish players with incremental support and per-competition stats.

    Args:
        player_filter: If set, only sync these specific players (list of rapidapi_id)
    """
    print(f"\n{'='*60}")
    print(f"SYNC: {team_info['name']} - {'FULL' if args.full else 'INCREMENTAL'} [tier: {getattr(args, 'tier', 'all')}]")
    if player_filter:
        names = [POLISH_PLAYERS.get(pid, {}).get('name', str(pid)) for pid in player_filter]
        print(f"Player filter: {names}")
    print(f"{'='*60}")

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Create rate limiter
        limiter = RateLimiter(session)
        month_used = await limiter._count_monthly_requests()
        print(f"  🔧 Rate limiter initialized (max {MAX_REQUESTS_PER_MINUTE}/min, {MAX_REQUESTS_PER_HOUR}/hour)")
        print(f"  📊 Monthly API usage: {month_used}/{MAX_REQUESTS_PER_MONTH}")
        if month_used >= MAX_REQUESTS_PER_MONTH:
            print(f"  🛑 Monthly limit reached! Sync aborted.")
            return 0

        # Collect stats per competition - typed defaultdict
        stats_by_competition: defaultdict[tuple[str, str, int], defaultdict[int, PlayerMatchStats]] = (
            defaultdict(lambda: defaultdict(_make_player_stats))
        )

        # Track processed matches for dedup
        matches_processed = 0
        api_calls = 0
        new_matches_synced = 0  # Track total new matches synced across all competitions

        for competition in team_info.get("competitions", []):
            comp_name = competition["name"]
            comp_id = competition["league_id"]
            comp_type = map_competition_type(comp_name)

            # Tier filtering: skip competitions not in selected tier
            tier = getattr(args, 'tier', 'all')
            if tier != "all":
                comp_tier = get_tier_for_league(comp_id)
                if comp_tier != tier:
                    continue

            print(f"\n📥 {comp_name} ({comp_type})...")

            # Check sync state for incremental
            if not args.full and not args.force:
                sync_state = await get_sync_state(session, team_id, comp_id)
                if sync_state and sync_state.next_sync_at:
                    if datetime.utcnow() < sync_state.next_sync_at:
                        print(f"   ⏭️ Cache valid until {sync_state.next_sync_at}, skipping")
                        continue

            # Fetch matches from API (with rate limiting)
            matches = []
            try:
                matches = await get_matches_by_league(comp_id, client, limiter)
                api_calls += 1
            except Exception as e:
                print(f"   ⚠️ League endpoint failed: {e}")

            # Fallback to search when league returns no matches or failed
            if len(matches) == 0:
                try:
                    matches = await get_matches_by_search(
                        team_info["name"].replace("FC ", ""), comp_id, client, limiter
                    )
                    api_calls += 1
                except Exception as e:
                    print(f"   ❌ Search also failed: {e}")
                    continue

            print(f"   API returned {len(matches)} total matches")

            # Filter: team matches + finished
            team_matches = []

            for m in matches:
                if not isinstance(m, dict):
                    continue
                home = m.get("home", {}) or {}
                away = m.get("away", {}) or {}
                try:
                    home_id_raw = home.get("id") if isinstance(home, dict) else None
                    away_id_raw = away.get("id") if isinstance(away, dict) else None
                    home_id = int(home_id_raw) if home_id_raw is not None else None  # type: ignore[arg-type]
                    away_id = int(away_id_raw) if away_id_raw is not None else None  # type: ignore[arg-type]
                except (ValueError, TypeError):
                    continue

                status = m.get("status", {})
                is_finished = status.get("finished", False) if isinstance(status, dict) else False

                if (home_id == team_id or away_id == team_id) and is_finished:
                    team_matches.append({
                        "event_id": m.get("id"),
                        "is_home": home_id == team_id,
                        "home_name": home.get("name"),
                        "away_name": away.get("name"),
                    })

            print(f"   {team_info['name']} finished matches: {len(team_matches)}")

            if not team_matches:
                continue

            # For incremental: get last synced match_id
            last_match_id = 0
            if not args.full:
                sync_state = await get_sync_state(session, team_id, comp_id)
                if sync_state:
                    last_match_id = sync_state.last_match_id or 0

            # Process each match
            comp_new_matches = 0
            max_match_id = last_match_id

            for match in team_matches:
                event_id = int(match["event_id"]) if match["event_id"] else 0

                # Incremental: skip already processed (unless --full or --player --force)
                if not args.full and not (player_filter and args.force) and event_id <= last_match_id:
                    continue

                # Dedup: skip if already synced (unless --full or --player --force)
                if not args.full and not (player_filter and args.force) and await is_match_synced(session, event_id, team_id):
                    continue

                is_home = match["is_home"]
                print(f"   [{event_id}] {match['home_name']} vs {match['away_name']}...", end=" ")

                if args.dry_run:
                    print("DRY RUN")
                    comp_new_matches += 1
                    max_match_id = max(max_match_id, event_id)
                    continue

                try:
                    lineup_data = await get_lineup(event_id, is_home, client, limiter)
                    api_calls += 1

                    lineup = lineup_data.get("response", {}).get("lineup", {})
                    if not lineup:
                        print("NO LINEUP")
                        continue

                    starters = lineup.get("starters", [])
                    subs = lineup.get("subs", [])
                    starter_ids = {p.get("id") for p in starters}
                    all_players = starters + subs

                    found_players = []
                    gk_playing = None
                    processed_players = set()  # Dedup: prevent counting same player twice

                    for player in all_players:
                        player_rapid_id = player.get("id")

                        # Dedup: skip if already processed this player in this match
                        if player_rapid_id in processed_players:
                            continue
                        processed_players.add(player_rapid_id)

                        # Filter by POLISH_PLAYERS
                        if player_rapid_id not in POLISH_PLAYERS:
                            continue

                        # Filter by specific players if --player or --gk-only option
                        if player_filter and player_rapid_id not in player_filter:
                            continue

                        is_starter = player_rapid_id in starter_ids
                        parsed = parse_player_performance(player, is_starter)

                        if not parsed or parsed["minutes"] == 0:
                            continue

                        # Get or create player in DB
                        result = await session.execute(
                            select(Player).where(Player.rapidapi_id == player_rapid_id)
                        )
                        player_db = result.scalar_one_or_none()

                        if not player_db:
                            player_db = Player(
                                rapidapi_id=player_rapid_id,
                                name=POLISH_PLAYERS[player_rapid_id]["name"],
                                position=POLISH_PLAYERS[player_rapid_id]["position"],
                                team=team_info["name"],
                                league="Multiple",
                            )
                            session.add(player_db)
                            await session.flush()
                        else:
                            # Update existing player info (position, team)
                            player_db.position = POLISH_PLAYERS[player_rapid_id]["position"]
                            player_db.team = team_info["name"]

                        # Update stats for this competition
                        stats = stats_by_competition[(comp_type, comp_name, comp_id)][player_db.id]
                        stats["minutes"] += parsed["minutes"]
                        stats["goals"] += parsed["goals"]
                        stats["assists"] += parsed["assists"]
                        stats["yellow_cards"] += parsed["yellow_cards"]
                        stats["red_cards"] += parsed["red_cards"]
                        stats["matches_total"] += 1
                        if parsed["started"]:
                            stats["matches_started"] += 1
                        else:
                            stats["matches_subbed"] += 1

                        rating = player.get("performance", {}).get("rating")
                        if rating:
                            stats["ratings"].append(rating)

                        # Check if GK (use position from POLISH_PLAYERS or API fallback)
                        is_gk = (
                            POLISH_PLAYERS.get(player_rapid_id, {}).get("position") == "GK" or
                            player.get("positionId") == 11 or
                            player.get("usualPlayingPositionId") == 0
                        )
                        if is_gk:
                            gk_playing = (player_db.id, player_rapid_id)

                        found_players.append(f"{POLISH_PLAYERS[player_rapid_id]['name']} ({parsed['minutes']}')")

                        # Save heatmap position (skip GK - not useful for heatmaps)
                        if not is_gk and not args.dry_run:
                            # Try verticalLayout first (more intuitive: x=left-right, y=field position)
                            # Fall back to horizontalLayout if verticalLayout not available
                            v_layout = player.get("verticalLayout")
                            h_layout = player.get("horizontalLayout")
                            layout = v_layout or h_layout

                            if layout:
                                try:
                                    # verticalLayout: x=left-right (0=RIGHT, 1=LEFT from API), y=field position
                                    # horizontalLayout: x=field position, y=left-right (same convention)
                                    # We swap x/y and get consistent output: pos_x=field position, pos_y=left-right
                                    # pos_y convention: 0=RIGHT, 1=LEFT (from viewer perspective)
                                    if v_layout:
                                        pos_x_val = v_layout.get("y", 0)  # field position (defense=0, attack=1)
                                        pos_y_val = v_layout.get("x", 0)  # left-right (0=RIGHT=1=LEFT)
                                        zone_w = v_layout.get("width", 0)
                                        zone_h = v_layout.get("height", 0)
                                    else:
                                        # horizontalLayout has same convention
                                        pos_x_val = h_layout.get("x", 0)  # field position (defense=0, attack=1)
                                        pos_y_val = h_layout.get("y", 0)  # left-right (0=RIGHT=1=LEFT)
                                        zone_w = h_layout.get("width", 0)
                                        zone_h = h_layout.get("height", 0)

                                    # After swap:
                                    # pos_x = field position (defense=0, attack=1)
                                    # pos_y = left-right (0=RIGHT, 1=LEFT from viewer perspective)

                                    stmt = insert(PlayerHeatmapPosition).values(
                                        player_id=player_db.id,
                                        match_id=event_id,
                                        season="2025/26",
                                        pos_x=pos_x_val,
                                        pos_y=pos_y_val,
                                        zone_width=zone_w,
                                        zone_height=zone_h,
                                        competition_name=comp_name,
                                        competition_type=comp_type,
                                        formation=lineup.get("formation"),
                                        minutes_played=parsed["minutes"],
                                        is_starter=parsed["started"],
                                    ).on_conflict_do_update(
                                        constraint="uq_heatmap_player_match_season",
                                        set_={
                                            "pos_x": pos_x_val,
                                            "pos_y": pos_y_val,
                                            "zone_width": zone_w,
                                            "zone_height": zone_h,
                                            "minutes_played": parsed["minutes"],
                                            "is_starter": parsed["started"],
                                        }
                                    )
                                    await session.execute(stmt)
                                except Exception as e:
                                    print(f"   Heatmap save error: {e}")

                    # Fetch GK stats if needed
                    if gk_playing:
                        try:
                            match_score = await get_match_score(event_id, client, limiter)
                            match_stats = await get_match_all_stats(event_id, client, limiter)
                            api_calls += 2
                            gk_stats = extract_gk_match_stats(match_score, match_stats, is_home)
                            print(f"   GK stats: saves={gk_stats['saves']}, GA={gk_stats['goals_against']}, CS={gk_stats['clean_sheet']}")

                            stats = stats_by_competition[(comp_type, comp_name, comp_id)][gk_playing[0]]
                            stats["clean_sheets"] += 1 if gk_stats["clean_sheet"] else 0
                            stats["saves"] += gk_stats["saves"]
                            stats["goals_against"] += gk_stats["goals_against"]
                            stats["shots_on_target_against"] += gk_stats["shots_on_target_against"]
                        except Exception as e:
                            print(f"   GK error: {e}")
                            import traceback
                            traceback.print_exc()

                    if found_players:
                        # Mark match as synced only when Polish player was found
                        await mark_match_synced(session, event_id, team_id, comp_id)
                        print(f"FOUND: {', '.join(found_players)}")

                        comp_new_matches += 1
                        max_match_id = max(max_match_id, event_id)
                        matches_processed += 1
                    else:
                        print(f"[{event_id}] no Polish players found — will retry next sync")

                    await asyncio.sleep(0.1)

                except Exception as e:
                    print(f"ERROR: {e}")

            # Update sync state
            if not args.dry_run and comp_new_matches > 0:
                await update_sync_state(
                    session, team_id, team_info["name"],
                    comp_id, comp_name, max_match_id, comp_new_matches
                )
                print(f"   ✅ Synced {comp_new_matches} new matches")
            new_matches_synced += comp_new_matches  # Accumulate to outer counter

        # Save stats to database
        if args.dry_run:
            print(f"\n📊 DRY RUN - {new_matches_synced} matches would be checked for lineups")
            print(f"   Note: Actual synced matches depend on Polish players being in lineups")
            print(f"   API calls so far: {api_calls}")
            return new_matches_synced

        print(f"\n📊 Saving to database...")
        print(f"   API calls used: {api_calls}")

        # Save per-competition stats
        for (comp_type, comp_name, comp_id), player_stats in stats_by_competition.items():
            for player_db_id, stats in player_stats.items():
                if stats["matches_total"] == 0:
                    continue

                # Upsert to player_stats_by_competition
                result = await session.execute(
                    select(PlayerStatsByCompetition).where(
                        PlayerStatsByCompetition.player_id == player_db_id,
                        PlayerStatsByCompetition.season == CURRENT_SEASON,
                        PlayerStatsByCompetition.competition_type == comp_type,
                        PlayerStatsByCompetition.competition_name == comp_name,
                    )
                )
                comp_stats = result.scalar_one_or_none()

                if not comp_stats:
                    comp_stats = PlayerStatsByCompetition(
                        player_id=player_db_id,
                        season=CURRENT_SEASON,
                        competition_type=comp_type,
                        competition_name=comp_name,
                        competition_id=comp_id,
                    )
                    session.add(comp_stats)

                # Update values:
                # --full or --player: REPLACE (all matches reprocessed, we have complete data)
                # incremental: ADD to existing (only new matches processed)
                if args.full or (player_filter and args.force):
                    # Warning if new data has fewer matches than existing (data was likely corrupted)
                    existing_matches = int(comp_stats.matches_total or 0)
                    new_matches = stats["matches_total"]
                    if new_matches < existing_matches:
                        print(f"   ⚠️ OVERWRITE: {comp_name} new matches ({new_matches}) < existing ({existing_matches}) — correcting data")

                    # Full sync: overwrite with fresh data
                    comp_stats.matches_total = stats["matches_total"]
                    comp_stats.matches_started = stats["matches_started"]
                    comp_stats.matches_subbed = stats["matches_subbed"]
                    comp_stats.minutes_played = stats["minutes"]
                    comp_stats.goals = stats["goals"]
                    comp_stats.assists = stats["assists"]
                    comp_stats.yellow_cards = stats["yellow_cards"]
                    comp_stats.red_cards = stats["red_cards"]
                    avg_rating = sum(stats["ratings"]) / len(stats["ratings"]) if stats["ratings"] else 0
                    comp_stats.rating = round(avg_rating, 2)
                    comp_stats.g_per90 = calculate_per_90(stats["goals"], stats["minutes"])
                    comp_stats.a_per90 = calculate_per_90(stats["assists"], stats["minutes"])

                    # GK stats: overwrite
                    is_gk = stats["shots_on_target_against"] > 0 or stats["saves"] > 0
                    if is_gk:
                        comp_stats.clean_sheets = stats["clean_sheets"]
                        comp_stats.saves = stats["saves"]
                        comp_stats.goals_against = stats["goals_against"]
                        comp_stats.shots_on_target_against = stats["shots_on_target_against"]
                        if stats["shots_on_target_against"] > 0:
                            comp_stats.save_percentage = round(
                                stats["saves"] / stats["shots_on_target_against"] * 100, 1
                            )
                else:
                    # Incremental sync: ADD new stats to existing
                    old_minutes = int(comp_stats.minutes_played or 0)
                    old_rating = float(comp_stats.rating or 0)
                    old_cs = int(comp_stats.clean_sheets or 0)
                    old_saves = int(comp_stats.saves or 0)
                    old_ga = int(comp_stats.goals_against or 0)
                    old_sota = int(comp_stats.shots_on_target_against or 0)

                    comp_stats.matches_total = int(comp_stats.matches_total or 0) + stats["matches_total"]
                    comp_stats.matches_started = int(comp_stats.matches_started or 0) + stats["matches_started"]
                    comp_stats.matches_subbed = int(comp_stats.matches_subbed or 0) + stats["matches_subbed"]
                    comp_stats.minutes_played = old_minutes + stats["minutes"]
                    comp_stats.goals = int(comp_stats.goals or 0) + stats["goals"]
                    comp_stats.assists = int(comp_stats.assists or 0) + stats["assists"]
                    comp_stats.yellow_cards = int(comp_stats.yellow_cards or 0) + stats["yellow_cards"]
                    comp_stats.red_cards = int(comp_stats.red_cards or 0) + stats["red_cards"]

                    # Rating: weighted average
                    if stats["ratings"]:
                        total_minutes = old_minutes + stats["minutes"]
                        if total_minutes > 0:
                            new_avg = sum(stats["ratings"]) / len(stats["ratings"])
                            comp_stats.rating = round(
                                (old_rating * old_minutes + new_avg * stats["minutes"]) / total_minutes, 2
                            )

                    comp_stats.g_per90 = calculate_per_90(int(comp_stats.goals or 0), int(comp_stats.minutes_played or 0))
                    comp_stats.a_per90 = calculate_per_90(int(comp_stats.assists or 0), int(comp_stats.minutes_played or 0))

                    # GK stats: ADD to existing
                    is_gk = stats["shots_on_target_against"] > 0 or stats["saves"] > 0
                    if is_gk:
                        comp_stats.clean_sheets = old_cs + stats["clean_sheets"]
                        comp_stats.saves = old_saves + stats["saves"]
                        comp_stats.goals_against = old_ga + stats["goals_against"]
                        comp_stats.shots_on_target_against = old_sota + stats["shots_on_target_against"]
                        if comp_stats.shots_on_target_against > 0:
                            comp_stats.save_percentage = round(
                                int(comp_stats.saves or 0) / int(comp_stats.shots_on_target_against or 0) * 100, 1
                            )

                comp_stats.updated_at = datetime.utcnow()
                comp_stats.expires_at = datetime.utcnow() + timedelta(hours=CACHE_TTL_HOURS)

        # Aggregate to Season Total (player_stats)
        await aggregate_to_season_total(session, player_filter)

        return matches_processed


async def aggregate_to_season_total(session, player_filter: list[int] | None = None):
    """Aggregate all competition stats to player_stats (Season Total).

    Args:
        player_filter: If set, only aggregate these specific players (list of rapidapi_id)
    """
    print(f"\n📊 Aggregating to Season Total...")

    # Build query based on filter
    if player_filter:
        # Only aggregate specific players
        result = await session.execute(
            select(Player).where(Player.rapidapi_id.in_(player_filter))
        )
        print(f"   Filtering to {len(player_filter)} player(s)")
    else:
        # Aggregate all players
        result = await session.execute(select(Player))

    players = result.scalars().all()

    for player in players:
        # Get all competition stats for this player
        result = await session.execute(
            select(PlayerStatsByCompetition).where(
                PlayerStatsByCompetition.player_id == player.id,
                PlayerStatsByCompetition.season == CURRENT_SEASON,
            )
        )
        comp_stats_list = result.scalars().all()

        # Create empty PlayerStats for new players without matches
        if not comp_stats_list:
            # Check if PlayerStats already exists
            result = await session.execute(
                select(PlayerStats).where(
                    PlayerStats.player_id == player.id,
                    PlayerStats.season == CURRENT_SEASON,
                )
            )
            db_stats = result.scalar_one_or_none()

            if not db_stats:
                # Create empty stats record for new player
                db_stats = PlayerStats(
                    player_id=player.id,
                    season=CURRENT_SEASON,
                    matches_total=0,
                    matches_started=0,
                    matches_subbed=0,
                    minutes_played=0,
                    goals=0,
                    assists=0,
                    yellow_cards=0,
                    red_cards=0,
                    rating=0.0,
                    g_per90=0.0,
                    a_per90=0.0,
                )
                session.add(db_stats)
                print(f"   {player.name}: Created empty stats (no matches yet)")
            continue

        # Aggregate
        total = {
            "matches_total": 0, "matches_started": 0, "matches_subbed": 0,
            "minutes_played": 0, "goals": 0, "assists": 0,
            "yellow_cards": 0, "red_cards": 0, "ratings": [],
            "clean_sheets": 0, "saves": 0, "goals_against": 0,
            "shots_on_target_against": 0,
        }

        for cs in comp_stats_list:
            total["matches_total"] += cs.matches_total
            total["matches_started"] += cs.matches_started
            total["matches_subbed"] += cs.matches_subbed
            total["minutes_played"] += cs.minutes_played
            total["goals"] += cs.goals
            total["assists"] += cs.assists
            total["yellow_cards"] += cs.yellow_cards
            total["red_cards"] += cs.red_cards
            if cs.rating:
                total["ratings"].append(float(cs.rating))
            if cs.clean_sheets:
                total["clean_sheets"] += cs.clean_sheets
            if cs.saves:
                total["saves"] += cs.saves
            if cs.goals_against:
                total["goals_against"] += cs.goals_against
            if cs.shots_on_target_against:
                total["shots_on_target_against"] += cs.shots_on_target_against

        # Get or create PlayerStats
        result = await session.execute(
            select(PlayerStats).where(
                PlayerStats.player_id == player.id,
                PlayerStats.season == CURRENT_SEASON,
            )
        )
        db_stats = result.scalar_one_or_none()

        if not db_stats:
            db_stats = PlayerStats(player_id=player.id, season=CURRENT_SEASON)
            session.add(db_stats)

        # Update Season Total
        avg_rating = sum(total["ratings"]) / len(total["ratings"]) if total["ratings"] else 0
        db_stats.matches_total = total["matches_total"]
        db_stats.matches_started = total["matches_started"]
        db_stats.matches_subbed = total["matches_subbed"]
        db_stats.minutes_played = total["minutes_played"]
        db_stats.goals = total["goals"]
        db_stats.assists = total["assists"]
        db_stats.yellow_cards = total["yellow_cards"]
        db_stats.red_cards = total["red_cards"]
        db_stats.rating = round(avg_rating, 2)
        db_stats.g_per90 = calculate_per_90(total["goals"], total["minutes_played"])
        db_stats.a_per90 = calculate_per_90(total["assists"], total["minutes_played"])
        db_stats.updated_at = datetime.utcnow()
        db_stats.expires_at = datetime.utcnow() + timedelta(hours=CACHE_TTL_HOURS)

        # GK totals
        is_gk = total["saves"] > 0 or total["clean_sheets"] > 0
        if is_gk and total["shots_on_target_against"] > 0:
            db_stats.clean_sheets = total["clean_sheets"]
            db_stats.saves = total["saves"]
            db_stats.goals_against = total["goals_against"]
            db_stats.save_percentage = round(
                total["saves"] / total["shots_on_target_against"] * 100, 1
            )
            if total["matches_total"] > 0:
                db_stats.clean_sheets_percentage = round(
                    total["clean_sheets"] / total["matches_total"] * 100, 1
                )
            db_stats.goals_against_per90 = calculate_per_90(
                total["goals_against"], total["minutes_played"]
            )

        print(f"   {player.name}: {total['matches_total']} matches, {total['goals']}G, {total['assists']}A")


def _extract_match_date(match: dict) -> datetime | None:
    """Extract date from match data. Tries multiple field names from the API."""
    # Try common date field names from RapidAPI Football
    for field in ["date", "start_date", "timestamp", "kickoff", "datetime", "utcDate"]:
        val = match.get(field)
        if val:
            try:
                if isinstance(val, (int, float)):
                    return datetime.utcfromtimestamp(val)
                if isinstance(val, str):
                    # ISO format: "2025-03-12T20:00:00" or "2025-03-12"
                    val = val.replace("Z", "+00:00").split("+")[0].split(".")[0]
                    return datetime.fromisoformat(val)
            except (ValueError, OSError):
                continue

    # Check nested status object for date
    status = match.get("status", {})
    if isinstance(status, dict):
        for field in ["startDate", "startTime", "kickoff"]:
            val = status.get(field)
            if val:
                try:
                    if isinstance(val, (int, float)):
                        return datetime.utcfromtimestamp(val)
                    if isinstance(val, str):
                        val = val.replace("Z", "+00:00").split("+")[0].split(".")[0]
                        return datetime.fromisoformat(val)
                except (ValueError, OSError):
                    continue
    return None


async def get_matches_by_league(league_id: int, client: httpx.AsyncClient, limiter: RateLimiter | None = None) -> list:
    """Get all matches from a league with rate limiting and retry on API failures."""
    for attempt in range(API_RETRY_ATTEMPTS):
        if limiter:
            await limiter.acquire()

        headers = {
            "x-rapidapi-key": API_KEY,
            "x-rapidapi-host": API_HOST,
        }

        response = await client.get(
            f"https://{API_HOST}/football-get-all-matches-by-league",
            headers=headers,
            params={"leagueid": league_id},
        )

        # 503: retry with backoff (may be temporary rate limit)
        if response.status_code == 503:
            if attempt < API_RETRY_ATTEMPTS - 1:
                delay = API_RETRY_BASE_DELAY * (3 ** attempt)
                print(f"   ⚠️ API 503 dla ligi {league_id}, retry {attempt + 1}/{API_RETRY_ATTEMPTS} (wait {delay}s)")
                await asyncio.sleep(delay)
                continue
            else:
                print(f"   ❌ API 503 po {API_RETRY_ATTEMPTS} próbach dla ligi {league_id}")
                return []

        response.raise_for_status()
        data = response.json()

        try:
            _check_api_status(data)
        except APIResponseError as e:
            if attempt < API_RETRY_ATTEMPTS - 1:
                delay = API_RETRY_BASE_DELAY * (3 ** attempt)
                print(f"  ⚠️ API retry {attempt + 1}/{API_RETRY_ATTEMPTS} (wait {delay}s) for league {league_id}: {e}")
                await asyncio.sleep(delay)
                continue
            else:
                print(f"  ❌ API failed after {API_RETRY_ATTEMPTS} attempts for league {league_id}: {e}")
                raise

        # Parse nested structure: response.matches
        response_data = data.get("response", {})
        if isinstance(response_data, dict):
            matches = response_data.get("matches", [])
        else:
            matches = response_data if isinstance(response_data, list) else []

        return matches if isinstance(matches, list) else []

    return []


async def get_matches_by_search(team_name: str, league_id: int, client: httpx.AsyncClient, limiter: RateLimiter | None = None) -> list:
    """Get matches from a league using search endpoint (for leagues like Supercopa) with rate limiting and retry on API failures."""
    for attempt in range(API_RETRY_ATTEMPTS):
        if limiter:
            await limiter.acquire()

        headers = {
            "x-rapidapi-key": API_KEY,
            "x-rapidapi-host": API_HOST,
        }

        response = await client.get(
            f"https://{API_HOST}/football-matches-search",
            headers=headers,
            params={"search": team_name},
        )

        # 503: retry with backoff (may be temporary rate limit)
        if response.status_code == 503:
            if attempt < API_RETRY_ATTEMPTS - 1:
                delay = API_RETRY_BASE_DELAY * (3 ** attempt)
                print(f"   ⚠️ API 503 dla search '{team_name}', retry {attempt + 1}/{API_RETRY_ATTEMPTS} (wait {delay}s)")
                await asyncio.sleep(delay)
                continue
            else:
                print(f"   ❌ API 503 po {API_RETRY_ATTEMPTS} próbach dla search '{team_name}'")
                return []

        response.raise_for_status()
        data = response.json()

        try:
            _check_api_status(data)
        except APIResponseError as e:
            if attempt < API_RETRY_ATTEMPTS - 1:
                delay = API_RETRY_BASE_DELAY * (3 ** attempt)
                print(f"  ⚠️ API retry {attempt + 1}/{API_RETRY_ATTEMPTS} (wait {delay}s) for search '{team_name}': {e}")
                await asyncio.sleep(delay)
                continue
            else:
                print(f"  ❌ API failed after {API_RETRY_ATTEMPTS} attempts for search '{team_name}': {e}")
                raise

        # Parse search results
        suggestions = data.get("response", {}).get("suggestions", [])

        # Filter to only match type and specific league_id
        matches = []
        for s in suggestions:
            if s.get("type") == "match" and s.get("leagueId") == league_id:
                # Convert to same format as get_matches_by_league
                match_data = {
                    "id": s.get("id"),
                    "home": {
                        "id": s.get("homeTeamId"),
                        "name": s.get("homeTeamName"),
                    },
                    "away": {
                        "id": s.get("awayTeamId"),
                        "name": s.get("awayTeamName"),
                    },
                    "status": s.get("status", {}),
                }
                matches.append(match_data)

        return matches

    return []


async def get_lineup(event_id: int, is_home: bool, client: httpx.AsyncClient, limiter: RateLimiter | None = None) -> dict[str, Any]:
    """Get lineup for a match with rate limiting and retry on API failures."""
    endpoint = "football-get-hometeam-lineup" if is_home else "football-get-awayteam-lineup"

    for attempt in range(API_RETRY_ATTEMPTS):
        if limiter:
            await limiter.acquire()

        headers = {
            "x-rapidapi-key": API_KEY,
            "x-rapidapi-host": API_HOST,
        }

        response = await client.get(
            f"https://{API_HOST}/{endpoint}",
            headers=headers,
            params={"eventid": event_id},
        )

        if response.status_code == 503:
            if attempt < API_RETRY_ATTEMPTS - 1:
                delay = API_RETRY_BASE_DELAY * (3 ** attempt)
                print(f"      ⚠️ API 503 dla lineup {event_id}, retry {attempt + 1}/{API_RETRY_ATTEMPTS} (wait {delay}s)")
                await asyncio.sleep(delay)
                continue
            else:
                print(f"      ❌ API 503 po {API_RETRY_ATTEMPTS} próbach dla lineup {event_id}")
                return {}

        response.raise_for_status()
        data = response.json()

        try:
            _check_api_status(data)
            return data
        except APIResponseError as e:
            if attempt < API_RETRY_ATTEMPTS - 1:
                delay = API_RETRY_BASE_DELAY * (3 ** attempt)  # 5s, 15s, 45s
                print(f"      ⚠️ API retry {attempt + 1}/{API_RETRY_ATTEMPTS} (wait {delay}s): {e}")
                await asyncio.sleep(delay)
            else:
                print(f"      ❌ API failed after {API_RETRY_ATTEMPTS} attempts: {e}")
                raise

    raise APIResponseError(f"Lineup fetch failed for event {event_id} after {API_RETRY_ATTEMPTS} attempts")


async def get_match_score(event_id: int, client: httpx.AsyncClient, limiter: RateLimiter | None = None) -> dict[str, Any]:
    """Get match score for GK stats (goals conceded, clean sheets) with rate limiting and retry."""
    for attempt in range(API_RETRY_ATTEMPTS):
        if limiter:
            await limiter.acquire()

        headers = {
            "x-rapidapi-key": API_KEY,
            "x-rapidapi-host": API_HOST,
        }

        response = await client.get(
            f"https://{API_HOST}/football-get-match-score",
            headers=headers,
            params={"eventid": event_id},
        )

        if response.status_code == 503:
            if attempt < API_RETRY_ATTEMPTS - 1:
                delay = API_RETRY_BASE_DELAY * (3 ** attempt)
                print(f"      ⚠️ API 503 dla match score {event_id}, retry {attempt + 1}/{API_RETRY_ATTEMPTS} (wait {delay}s)")
                await asyncio.sleep(delay)
                continue
            else:
                print(f"      ❌ API 503 po {API_RETRY_ATTEMPTS} próbach dla match score {event_id}")
                return {}

        response.raise_for_status()
        data = response.json()

        try:
            _check_api_status(data)
            return data
        except APIResponseError as e:
            if attempt < API_RETRY_ATTEMPTS - 1:
                delay = API_RETRY_BASE_DELAY * (3 ** attempt)
                print(f"      ⚠️ API retry {attempt + 1}/{API_RETRY_ATTEMPTS} (wait {delay}s) for match score {event_id}: {e}")
                await asyncio.sleep(delay)
            else:
                print(f"      ❌ API failed after {API_RETRY_ATTEMPTS} attempts for match score {event_id}: {e}")
                raise

    raise APIResponseError(f"Match score fetch failed for event {event_id} after {API_RETRY_ATTEMPTS} attempts")


async def get_match_all_stats(event_id: int, client: httpx.AsyncClient, limiter: RateLimiter | None = None) -> dict[str, Any]:
    """Get all match stats for GK stats (shots on target, saves) with rate limiting and retry."""
    for attempt in range(API_RETRY_ATTEMPTS):
        if limiter:
            await limiter.acquire()

        headers = {
            "x-rapidapi-key": API_KEY,
            "x-rapidapi-host": API_HOST,
        }

        response = await client.get(
            f"https://{API_HOST}/football-get-match-all-stats",
            headers=headers,
            params={"eventid": event_id},
        )

        if response.status_code == 503:
            if attempt < API_RETRY_ATTEMPTS - 1:
                delay = API_RETRY_BASE_DELAY * (3 ** attempt)
                print(f"      ⚠️ API 503 dla match stats {event_id}, retry {attempt + 1}/{API_RETRY_ATTEMPTS} (wait {delay}s)")
                await asyncio.sleep(delay)
                continue
            else:
                print(f"      ❌ API 503 po {API_RETRY_ATTEMPTS} próbach dla match stats {event_id}")
                return {}

        response.raise_for_status()
        data = response.json()

        try:
            _check_api_status(data)
            return data
        except APIResponseError as e:
            if attempt < API_RETRY_ATTEMPTS - 1:
                delay = API_RETRY_BASE_DELAY * (3 ** attempt)
                print(f"      ⚠️ API retry {attempt + 1}/{API_RETRY_ATTEMPTS} (wait {delay}s) for match stats {event_id}: {e}")
                await asyncio.sleep(delay)
            else:
                print(f"      ❌ API failed after {API_RETRY_ATTEMPTS} attempts for match stats {event_id}: {e}")
                raise

    raise APIResponseError(f"Match stats fetch failed for event {event_id} after {API_RETRY_ATTEMPTS} attempts")


def extract_gk_match_stats(match_score_data: dict[str, Any], match_stats_data: dict[str, Any], is_home: bool) -> dict[str, Any]:
    """
    Extract goalkeeper stats from match data.

    Stats arrays are [home_value, away_value].

    Returns:
        {
            "goals_against": int,
            "saves": int,
            "shots_on_target_against": int,
            "clean_sheet": bool
        }
    """
    result = {
        "goals_against": 0,
        "saves": 0,
        "shots_on_target_against": 0,
        "clean_sheet": False,
    }

    try:
        # Get scores - extract goals conceded
        scores = match_score_data.get("response", {}).get("scores", [])
        if len(scores) >= 2:
            if is_home:
                result["goals_against"] = scores[1].get("score", 0) if len(scores) > 1 else 0
            else:
                result["goals_against"] = scores[0].get("score", 0)
            result["clean_sheet"] = result["goals_against"] == 0

        # Get match stats - shots on target and keeper saves
        all_stats = match_stats_data.get("response", {}).get("stats", [])

        for category in all_stats:
            for stat in category.get("stats", []):
                stats_values = stat.get("stats", [])
                if len(stats_values) < 2:
                    continue

                # ShotsOnTarget - shots faced by GK
                if stat.get("key") == "ShotsOnTarget":
                    result["shots_on_target_against"] = stats_values[1] if is_home else stats_values[0]

                # keeper_saves - saves made by GK
                if stat.get("key") == "keeper_saves":
                    result["saves"] = stats_values[0] if is_home else stats_values[1]

    except Exception as e:
        print(f"Error extracting GK stats: {e}")

    return result


def parse_player_performance(player: dict, is_starter: bool) -> dict | None:
    """
    Parse player performance from lineup data.

    Args:
        player: Player data dict
        is_starter: True if player is in starters list, False if in subs

    Returns: {minutes, goals, assists, started, yellow_cards, red_cards} or None if didn't play
    """
    performance = player.get("performance", {})

    result = {
        "minutes": 0,  # Default: didn't play
        "goals": 0,
        "assists": 0,
        "yellow_cards": 0,
        "red_cards": 0,
        "started": False,
    }

    # Check for substitution events first
    sub_events = performance.get("substitutionEvents", [])

    if is_starter:
        # Starter: default 90 minutes unless subbed out
        result["minutes"] = 90
        result["started"] = True

        for sub in sub_events:
            sub_type = sub.get("type", "").lower()
            sub_time = sub.get("time", 0)

            if sub_type == "subout":
                result["minutes"] = sub_time
    else:
        # Substitute: default 0 minutes unless subbed in
        result["minutes"] = 0
        result["started"] = False

        for sub in sub_events:
            sub_type = sub.get("type", "").lower()
            sub_time = sub.get("time", 0)

            if sub_type == "subin":
                # Calculate minutes played (minimum 1 if subbed in at 90')
                result["minutes"] = max(1, 90 - sub_time)

    # If still 0 minutes, check if player has events or rating (API may lack substitutionEvents)
    if result["minutes"] == 0:
        has_events = bool(performance.get("events"))
        has_rating = performance.get("rating") is not None
        if has_events or has_rating:
            result["minutes"] = 1  # Played but unknown exact minutes
        else:
            return None

    # Parse events (goals, assists, cards)
    events = performance.get("events", [])
    for event in events:
        event_type = event.get("type", "").lower()
        if event_type == "goal":
            result["goals"] += 1
        elif event_type == "assist":
            result["assists"] += 1
        elif event_type == "yellowcard":
            result["yellow_cards"] += 1
        elif event_type == "redcard":
            result["red_cards"] += 1

    return result


async def main():
    """Main sync function with CLI support."""
    args = parse_args()

    # Handle --gk-only option: filter to goalkeepers only
    if args.gk_only:
        player_filter = [pid for pid, info in POLISH_PLAYERS.items() if info.get("position") == "GK"]
        gk_names = [POLISH_PLAYERS[pid]["name"] for pid in player_filter]
        print("=" * 60)
        print(f"🔄 SYNC: Goalkeepers Only")
        print("=" * 60)
        print(f"API Host: {API_HOST}")
        print(f"Season: {CURRENT_SEASON}")
        print(f"Goalkeepers: {gk_names}")
        if args.dry_run:
            print("🔍 DRY RUN MODE - No changes will be made")
        if args.force:
            print("⚠️ Force mode - ignoring cache")
        print()
    # Handle --player option: find team and filter to single player
    elif args.player:
        if args.player not in POLISH_PLAYERS:
            print(f"❌ Player {args.player} not found in POLISH_PLAYERS")
            print(f"   Available: {list(POLISH_PLAYERS.keys())}")
            return
        if args.player not in PLAYER_TEAMS:
            print(f"❌ Player {args.player} not found in PLAYER_TEAMS mapping")
            print(f"   Add the player's team_id to PLAYER_TEAMS dict")
            return

        player_filter = [args.player]
        player_name = POLISH_PLAYERS[args.player]["name"]
        team_id = PLAYER_TEAMS[args.player]

        # Override args.team to sync only this player's team
        args.team = team_id

        print("=" * 60)
        print(f"🔄 SYNC: Single Player ({player_name})")
        print("=" * 60)
        print(f"API Host: {API_HOST}")
        print(f"Season: {CURRENT_SEASON}")
        print(f"Player: {player_name} (id={args.player})")
        print(f"Team: {TEAMS[team_id]['name']} (id={team_id})")
        if args.force:
            print("⚠️ Force mode - ignoring cache")
        print()
    else:
        player_filter = None
        mode = "FULL" if args.full else "INCREMENTAL"
        tier = getattr(args, 'tier', 'all')
        print("=" * 60)
        print(f"🔄 SYNC: Polish Players ({mode}) [tier: {tier}]")
        print("=" * 60)
        print(f"API Host: {API_HOST}")
        print(f"Season: {CURRENT_SEASON}")
        print(f"Tier: {tier}")
        if tier != "all":
            print(f"  TOP leagues: {[c['name'] for t in TEAMS.values() for c in t['competitions'] if c['league_id'] in TOP_LEAGUE_IDS]}")
            print(f"  European cups: {[c['name'] for t in TEAMS.values() for c in t['competitions'] if c['league_id'] in EUROPEAN_CUP_IDS]}")
            print(f"  Niche leagues: {[c['name'] for t in TEAMS.values() for c in t['competitions'] if c['league_id'] in NICHE_LEAGUE_IDS]}")
        else:
            print(f"Players: {[p['name'] for p in POLISH_PLAYERS.values()]}")
        if args.dry_run:
            print("🔍 DRY RUN MODE - No changes will be made")
        if args.force:
            print("⚠️ Force mode - ignoring cache")
        print()

    # Initialize team to None (set by --player option)
    if not hasattr(args, 'team'):
        args.team = None

    total_matches = 0

    async with AsyncSessionLocal() as session:
        teams_to_sync = {args.team: TEAMS[args.team]} if args.team and args.team in TEAMS else TEAMS

        for team_id, team_info in teams_to_sync.items():
            try:
                matches = await sync_team_v2(team_id, team_info, session, args, player_filter)
                total_matches += matches
            except Exception as e:
                print(f"❌ Error syncing {team_info['name']}: {e}")
                import traceback
                traceback.print_exc()

        if not args.dry_run:
            await session.commit()

    print("\n" + "=" * 60)
    if args.dry_run:
        print(f"🔍 DRY RUN COMPLETE: {total_matches} matches would be checked for lineups")
        print("   Run without --dry-run to see actual sync results")
    else:
        print(f"✅ SYNC COMPLETE: {total_matches} matches processed")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
