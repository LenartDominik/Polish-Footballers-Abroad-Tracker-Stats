"""Test: Check lineup structure for one Barcelona match."""

import asyncio
import os
import httpx
import json
from dotenv import load_dotenv

load_dotenv()

API_HOST = "free-api-live-football-data.p.rapidapi.com"
API_KEY = os.getenv("RAPIDAPI_KEY")


async def test_lineup():
    print("=" * 60)
    print("TEST: Lineup Structure")
    print("=" * 60)

    headers = {
        "x-rapidapi-key": API_KEY,
        "x-rapidapi-host": API_HOST,
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        # First, get a Barcelona match ID
        print("\n1. Getting Barcelona match ID...")
        response = await client.get(
            f"https://{API_HOST}/football-get-all-matches-by-league",
            headers=headers,
            params={"leagueid": 87},  # La Liga
        )

        data = response.json()

        # Parse nested structure: response.matches
        response_data = data.get("response", {})
        if isinstance(response_data, dict):
            matches = response_data.get("matches", [])
        else:
            matches = response_data if isinstance(response_data, list) else []

        print(f"   Total matches: {len(matches)}")

        barca_match = None
        barca_event_id = None

        for m in matches:
            if not isinstance(m, dict):
                continue

            home = m.get("home", {}) or {}
            away = m.get("away", {}) or {}

            try:
                home_id = int(home.get("id")) if isinstance(home, dict) and home.get("id") else None
                away_id = int(away.get("id")) if isinstance(away, dict) and away.get("id") else None
            except:
                continue

            if home_id == 8634 or away_id == 8634:
                barca_match = m
                barca_event_id = m.get("id")
                break

        if not barca_match:
            print("   No Barcelona match found!")
            return

        print(f"   Found match: {barca_match.get('home', {}).get('name')} vs {barca_match.get('away', {}).get('name')}")
        print(f"   Event ID: {barca_event_id}")

        # Determine if Barca is home or away
        home = barca_match.get("home", {}) or {}
        is_home = isinstance(home, dict) and home.get("id") and int(home.get("id")) == 8634

        print(f"   Barca is: {'HOME' if is_home else 'AWAY'}")

        # Get lineup
        print(f"\n2. Getting lineup...")
        endpoint = "football-get-hometeam-lineup" if is_home else "football-get-awayteam-lineup"

        response = await client.get(
            f"https://{API_HOST}/{endpoint}",
            headers=headers,
            params={"eventid": barca_event_id},
        )

        print(f"   Status: {response.status_code}")

        if response.status_code == 200:
            lineup_data = response.json()

            # Save full response to file for inspection
            with open("lineup_debug.json", "w", encoding="utf-8") as f:
                json.dump(lineup_data, f, indent=2, default=str)

            print(f"\n3. Full response saved to lineup_debug.json")
            print(f"\n   Top-level keys: {list(lineup_data.keys())}")

            response_data = lineup_data.get("response", {})
            print(f"   Response keys: {list(response_data.keys()) if isinstance(response_data, dict) else type(response_data)}")

            # Show structure
            print(f"\n4. Full lineup response (first 5000 chars):")
            print(json.dumps(lineup_data, indent=2, default=str)[:5000])

        else:
            print(f"   Error: {response.text[:500]}")


if __name__ == "__main__":
    asyncio.run(test_lineup())
