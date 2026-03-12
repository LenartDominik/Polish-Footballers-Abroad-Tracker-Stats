"""Free API Live Football Data client for fetching player data."""

from typing import Optional, List, Dict, Any

import httpx
import structlog

from app.core.config import settings

logger = structlog.get_logger()


class RapidAPIClient:
    """Client for Free API Live Football Data (RapidAPI)."""

    def __init__(self):
        self.base_url = f"https://{settings.rapidapi_host}"
        self.headers = {
            "x-rapidapi-key": settings.rapidapi_key,
            "x-rapidapi-host": settings.rapidapi_host,
        }
        self.timeout = httpx.Timeout(30.0)

    async def get_players_by_team(self, team_id: int) -> List[Dict[str, Any]]:
        """
        Get all players from a team.

        Endpoint: /football-get-list-player?teamid=XXX

        Response structure:
        {
          "status": "success",
          "response": {
            "list": {
              "squad": [
                {"title": "keepers", "members": [...]},
                {"title": "defenders", "members": [...]},
                {"title": "midfielders", "members": [...]},
                {"title": "attackers", "members": [...]}
              ]
            }
          }
        }

        Each player has:
        - id, name, shirtNumber, ccode, cname
        - goals, assists, penalties, ycards, rcards
        - rating, positionIds, positionIdsDesc
        - height, age, dateOfBirth, transferValue
        - injury (null or {id, expectedReturn})
        """
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                logger.info("Fetching players", team_id=team_id)
                response = await client.get(
                    f"{self.base_url}/football-get-list-player",
                    headers=self.headers,
                    params={"teamid": team_id},
                )
                response.raise_for_status()
                data = response.json()

                # Parse nested structure
                squad = data.get("response", {}).get("list", {}).get("squad", [])
                all_players = []

                for group in squad:
                    members = group.get("members", [])
                    for player in members:
                        # Skip coaches
                        if group.get("title") == "coach":
                            continue
                        # Add group info
                        player["squad_group"] = group.get("title")
                        all_players.append(player)

                logger.info("Players fetched", team_id=team_id, count=len(all_players))
                return all_players

            except httpx.HTTPError as e:
                logger.error("Failed to fetch players", team_id=team_id, error=str(e))
                raise

    async def get_player_detail(self, player_id: int) -> Dict[str, Any]:
        """
        Get player details.

        Endpoint: /football-get-player-detail?playerid=XXX

        Returns:
        - Height, Shirt, Age
        - Preferred foot, Country
        - Market value, Contract end
        """
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                logger.info("Fetching player detail", player_id=player_id)
                response = await client.get(
                    f"{self.base_url}/football-get-player-detail",
                    headers=self.headers,
                    params={"playerid": player_id},
                )
                response.raise_for_status()
                data = response.json()
                return data.get("response", {}).get("detail", [])
            except httpx.HTTPError as e:
                logger.error("Failed to fetch player detail", player_id=player_id, error=str(e))
                raise

    async def get_lineup_home(self, event_id: int) -> Dict[str, Any]:
        """
        Get home team lineup for a match.

        Endpoint: /football-get-hometeam-lineup?eventid=XXX

        Returns:
        - Players with x, y coordinates (for heatmaps)
        - time (minutes played)
        - type: "goal", "assist", "SubIn"
        - height, width (pitch dimensions)
        """
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                logger.info("Fetching home lineup", event_id=event_id)
                response = await client.get(
                    f"{self.base_url}/football-get-hometeam-lineup",
                    headers=self.headers,
                    params={"eventid": event_id},
                )
                response.raise_for_status()
                return response.json()
            except httpx.HTTPError as e:
                logger.error("Failed to fetch home lineup", event_id=event_id, error=str(e))
                raise

    async def get_lineup_away(self, event_id: int) -> Dict[str, Any]:
        """
        Get away team lineup for a match.

        Endpoint: /football-get-awayteam-lineup?eventid=XXX
        """
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                logger.info("Fetching away lineup", event_id=event_id)
                response = await client.get(
                    f"{self.base_url}/football-get-awayteam-lineup",
                    headers=self.headers,
                    params={"eventid": event_id},
                )
                response.raise_for_status()
                return response.json()
            except httpx.HTTPError as e:
                logger.error("Failed to fetch away lineup", event_id=event_id, error=str(e))
                raise

    async def get_polish_players_from_team(self, team_id: int) -> List[Dict[str, Any]]:
        """
        Get Polish players from a specific team.

        Filters by ccode == "POL"
        """
        players = await self.get_players_by_team(team_id)
        polish_players = [p for p in players if p.get("ccode") == "POL"]
        logger.info("Polish players found", team_id=team_id, count=len(polish_players))
        return polish_players


def calculate_per_90(value: int, minutes: int) -> float:
    """Calculate per-90 statistic."""
    if minutes <= 0:
        return 0.0
    return round((value / minutes) * 90, 2)


def parse_player_for_db(player: Dict[str, Any], team_name: str = None) -> Dict[str, Any]:
    """
    Parse player data from API response to DB format.

    Maps API fields to our database schema.
    """
    return {
        "rapidapi_id": player.get("id"),
        "name": player.get("name"),
        "position": player.get("positionIdsDesc", "").split(",")[0],  # First position
        "team": team_name,
        "nationality": player.get("cname", "Poland"),
        # Stats
        "goals": player.get("goals", 0),
        "assists": player.get("assists", 0),
        "yellow_cards": player.get("ycards", 0),
        "red_cards": player.get("rcards", 0),
        "penalties_scored": player.get("penalties", 0),
        "rating": player.get("rating") or 0,
        # Additional info
        "shirt_number": player.get("shirtNumber"),
        "age": player.get("age"),
        "height": player.get("height"),
        "transfer_value": player.get("transferValue"),
        "injury": player.get("injury"),
    }


# Singleton instance
rapidapi_client = RapidAPIClient()
