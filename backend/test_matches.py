"""Test: Get all matches from La Liga and find Barcelona games."""

import asyncio
import os
import httpx
from dotenv import load_dotenv

load_dotenv()

API_HOST = "free-api-live-football-data.p.rapidapi.com"
API_KEY = os.getenv("RAPIDAPI_KEY")

LA_LIGA_ID = 87
BARCA_TEAM_ID = 8634


async def test_matches():
    print("=" * 60)
    print("TEST: Get All Matches by League (La Liga)")
    print("=" * 60)

    headers = {
        "x-rapidapi-key": API_KEY,
        "x-rapidapi-host": API_HOST,
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Get all La Liga matches
        response = await client.get(
            f"https://{API_HOST}/football-get-all-matches-by-league",
            headers=headers,
            params={"leagueid": LA_LIGA_ID},
        )

        print(f"Status: {response.status_code}")

        if response.status_code != 200:
            print(f"Error: {response.text[:500]}")
            return

        data = response.json()

        # Show structure
        print(f"\nResponse keys: {data.keys() if isinstance(data, dict) else type(data)}")

        # Find matches list
        matches = data.get("response", data.get("matches", data if isinstance(data, list) else []))
        if isinstance(matches, dict):
            matches = matches.get("list", matches.get("matches", []))

        print(f"Total matches: {len(matches) if isinstance(matches, list) else 'N/A'}")

        # Show first match structure
        if isinstance(matches, list) and len(matches) > 0:
            print(f"\nFirst match structure:")
            first = matches[0]
            for key, value in first.items():
                if isinstance(value, dict):
                    print(f"  {key}: {list(value.keys())[:5]}...")
                elif isinstance(value, list):
                    print(f"  {key}: [{len(value)} items]")
                else:
                    print(f"  {key}: {value}")

        # Find Barcelona matches - check ALL possible ID fields
        print(f"\n{'='*60}")
        print("Looking for Barcelona (ID: 8634)...")
        print(f"{'='*60}")

        barca_matches = []
        for m in (matches if isinstance(matches, list) else []):
            # Try different possible structures
            home = m.get("home", {}) or {}
            away = m.get("away", {}) or {}

            home_id = home.get("id") if isinstance(home, dict) else None
            away_id = away.get("id") if isinstance(away, dict) else None

            # Convert to int for comparison (API might return string)
            try:
                home_id = int(home_id) if home_id else None
                away_id = int(away_id) if away_id else None
            except (ValueError, TypeError):
                pass

            # Debug first 5 matches
            if len(barca_matches) < 5:
                print(f"  Match: home_id={home_id}, away_id={away_id}")

            if home_id == BARCA_TEAM_ID or away_id == BARCA_TEAM_ID:
                barca_matches.append(m)

        print(f"\n✅ Barcelona matches found: {len(barca_matches)}")

        # Show first 3 Barca matches
        for i, m in enumerate(barca_matches[:3]):
            event_id = m.get("id")
            home = m.get("home", {})
            away = m.get("away", {})
            home_name = home.get("name") if isinstance(home, dict) else "Home"
            away_name = away.get("name") if isinstance(away, dict) else "Away"
            print(f"  {i+1}. {home_name} vs {away_name} (event_id: {event_id})")


if __name__ == "__main__":
    asyncio.run(test_matches())
