"""Test script for Free API Live Football Data - Lewandowski only."""

import asyncio
import os
import httpx
from dotenv import load_dotenv

# Load .env
load_dotenv()

API_HOST = "free-api-live-football-data.p.rapidapi.com"
API_KEY = os.getenv("RAPIDAPI_KEY")

# Test data
LEWY_TEAM_ID = 8634  # FC Barcelona
LEWY_PLAYER_ID = 93447  # Robert Lewandowski
LA_LIGA_ID = 87


async def test_get_polish_players():
    """Test: Get Polish players from FC Barcelona."""
    print("\n" + "=" * 60)
    print("TEST: Polish Players from FC Barcelona")
    print("=" * 60)

    headers = {
        "x-rapidapi-key": API_KEY,
        "x-rapidapi-host": API_HOST,
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Get all players
        response = await client.get(
            f"https://{API_HOST}/football-get-list-player",
            headers=headers,
            params={"teamid": LEWY_TEAM_ID},
        )

        if response.status_code != 200:
            print(f"Error: {response.status_code}")
            return

        data = response.json()

        # Parse nested structure
        squad = data.get("response", {}).get("list", {}).get("squad", [])
        all_players = []

        for group in squad:
            members = group.get("members", [])
            for player in members:
                if group.get("title") != "coach":
                    player["squad_group"] = group.get("title")
                    all_players.append(player)

        # Filter Polish players
        polish_players = [p for p in all_players if p.get("ccode") == "POL"]

        print(f"\nTotal players: {len(all_players)}")
        print(f"Polish players: {len(polish_players)}")

        for p in polish_players:
            print("\n" + "-" * 40)
            print(f"🇵🇱 {p.get('name')}")
            print(f"   ID: {p.get('id')}")
            print(f"   Position: {p.get('positionIdsDesc')}")
            print(f"   Shirt: {p.get('shirtNumber')}")
            print(f"   Goals: {p.get('goals')}")
            print(f"   Assists: {p.get('assists')}")
            print(f"   Penalties: {p.get('penalties')}")
            print(f"   Yellow cards: {p.get('ycards')}")
            print(f"   Red cards: {p.get('rcards')}")
            print(f"   Rating: {p.get('rating')}")
            print(f"   Age: {p.get('age')}")
            print(f"   Height: {p.get('height')} cm")
            print(f"   Transfer value: €{p.get('transferValue', 0):,.0f}")


async def main():
    print("=" * 60)
    print("FREE API LIVE FOOTBALL DATA - POLISH PLAYERS TEST")
    print("=" * 60)
    print(f"API Host: {API_HOST}")
    print(f"API Key: {'SET' if API_KEY else 'NOT SET!'}")
    print(f"Team: FC Barcelona (ID: {LEWY_TEAM_ID})")

    if not API_KEY:
        print("\nERROR: RAPIDAPI_KEY not found in .env file!")
        return

    await test_get_polish_players()

    print("\n" + "=" * 60)
    print("TEST COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
