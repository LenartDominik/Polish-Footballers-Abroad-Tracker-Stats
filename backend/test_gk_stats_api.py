"""Test script to explore API endpoints for goalkeeper stats."""

import asyncio
import httpx
from dotenv import load_dotenv
from app.core.config import settings

load_dotenv()

API_HOST = "free-api-live-football-data.p.rapidapi.com"
API_KEY = settings.rapidapi_key

# Szczęsny's player ID
SZCZESNY_ID = 169718
BARCELONA_ID = 8634
LA_LIGA_ID = 87

headers = {
    "x-rapidapi-key": API_KEY,
    "x-rapidapi-host": API_HOST,
}


async def test_endpoints():
    """Test various API endpoints to understand structure."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        # 1. Get matches from La Liga
        print("=" * 60)
        print("1. TESTING: Get matches by league")
        print("=" * 60)

        response = await client.get(
            f"https://{API_HOST}/football-get-all-matches-by-league",
            headers=headers,
            params={"leagueid": LA_LIGA_ID},
        )
        data = response.json()

        matches = data.get("response", {}).get("matches", [])
        print(f"Total matches: {len(matches)}")

        # Find Barcelona matches
        barca_matches = []
        for m in matches:
            if not isinstance(m, dict):
                continue
            home = m.get("home", {}) or {}
            away = m.get("away", {}) or {}

            try:
                home_id = int(home.get("id")) if home.get("id") else None
                away_id = int(away.get("id")) if away.get("id") else None
            except (ValueError, TypeError):
                continue

            status = m.get("status", {})
            is_finished = status.get("finished", False) if isinstance(status, dict) else False

            if (home_id == BARCELONA_ID or away_id == BARCELONA_ID) and is_finished:
                barca_matches.append(m)

        print(f"Barcelona finished matches: {len(barca_matches)}")

        if barca_matches:
            # Take first match for testing
            match = barca_matches[0]
            event_id = match.get("id")
            home = match.get("home", {})
            away = match.get("away", {})

            print(f"\nExample match: {home.get('name')} vs {away.get('name')}")
            print(f"Event ID: {event_id}")
            print(f"Score: {home.get('score')} - {away.get('score')}")

            # 2. Test lineup endpoint (Barcelona's lineup)
            print("\n" + "=" * 60)
            print("2. TESTING: Get Barcelona lineup")
            print("=" * 60)

            is_barca_home = home.get("id") == BARCELONA_ID
            print(f"Barcelona is {'HOME' if is_barca_home else 'AWAY'}")

            # Get Barcelona's lineup
            if is_barca_home:
                endpoint = "football-get-hometeam-lineup"
            else:
                endpoint = "football-get-awayteam-lineup"

            response = await client.get(
                f"https://{API_HOST}/{endpoint}",
                headers=headers,
                params={"eventid": event_id},
            )
            lineup_data = response.json()

            lineup = lineup_data.get("response", {}).get("lineup", {})
            starters = lineup.get("starters", [])
            subs = lineup.get("subs", [])

            print(f"Starters: {len(starters)}, Subs: {len(subs)}")

            # Find Szczesny
            szcz_found = None
            for p in starters + subs:
                if p.get("id") == SZCZESNY_ID:
                    szcz_found = p
                    print(f"\n[OK] SZCZESNY FOUND in {'starters' if p in starters else 'subs'}!")
                    print(f"   ID: {p.get('id')}")
                    print(f"   Name: {p.get('name')}")
                    print(f"   Position: {p.get('position')}")
                    print(f"   Performance: {p.get('performance')}")
                    break

            if not szcz_found:
                print("\n[!] Szczesny NOT found in this match")

            # 3. Test match score endpoint
            print("\n" + "=" * 60)
            print("3. TESTING: Get match/event score")
            print("=" * 60)

            # Try different possible endpoint names
            score_endpoints = [
                "football-get-event-score",
                "football-get-match-score",
                "football-get-score",
                "football-get-match-details",
                "football-get-event-details",
            ]

            for endpoint in score_endpoints:
                try:
                    response = await client.get(
                        f"https://{API_HOST}/{endpoint}",
                        headers=headers,
                        params={"eventid": event_id},
                    )
                    if response.status_code == 200:
                        print(f"[OK] {endpoint} - SUCCESS")
                        data = response.json()
                        print(f"   Response keys: {data.keys()}")
                        print(f"   Full response: {data}")
                        break
                    else:
                        print(f"[--] {endpoint} - Status: {response.status_code}")
                except Exception as e:
                    print(f"[--] {endpoint} - Error: {e}")

            # 4. Test match stats endpoint
            print("\n" + "=" * 60)
            print("4. TESTING: Get match/event all stats")
            print("=" * 60)

            stats_endpoints = [
                "football-get-match-all-stats",
                "football-get-event-all-stats",
                "football-get-match-stats",
                "football-get-event-stats",
                "football-get-stats",
            ]

            for endpoint in stats_endpoints:
                try:
                    response = await client.get(
                        f"https://{API_HOST}/{endpoint}",
                        headers=headers,
                        params={"eventid": event_id},
                    )
                    if response.status_code == 200:
                        print(f"[OK] {endpoint} - SUCCESS")
                        data = response.json()
                        print(f"   Response keys: {data.keys()}")

                        # Pretty print the stats
                        import json
                        print(f"   Full response:\n{json.dumps(data, indent=2)}")
                        break
                    else:
                        print(f"[--] {endpoint} - Status: {response.status_code}")
                except Exception as e:
                    print(f"[--] {endpoint} - Error: {e}")

            # 5. Check what's already in the match data
            print("\n" + "=" * 60)
            print("5. CHECKING: Match data structure")
            print("=" * 60)

            import json
            print(f"Match keys: {match.keys()}")
            print(f"Full match data:\n{json.dumps(match, indent=2)}")


async def check_all_barca_keepers():
    """Check who was GK in all Barcelona matches."""
    print("\n" + "=" * 60)
    print("CHECKING ALL BARCELONA GOALKEEPERS")
    print("=" * 60)

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Get all La Liga matches
        response = await client.get(
            f"https://{API_HOST}/football-get-all-matches-by-league",
            headers=headers,
            params={"leagueid": LA_LIGA_ID},
        )
        data = response.json()
        matches = data.get("response", {}).get("matches", [])

        barca_matches = []

        for m in matches:
            if not isinstance(m, dict):
                continue

            home = m.get("home", {}) or {}
            away = m.get("away", {}) or {}

            try:
                home_id = int(home.get("id")) if home.get("id") else None
                away_id = int(away.get("id")) if away.get("id") else None
            except (ValueError, TypeError):
                continue

            status = m.get("status", {})
            is_finished = status.get("finished", False) if isinstance(status, dict) else False

            if (home_id == BARCELONA_ID or away_id == BARCELONA_ID) and is_finished:
                barca_matches.append(m)

        # Sort by date
        barca_matches.sort(key=lambda x: x.get("status", {}).get("utcTime", "") if isinstance(x.get("status"), dict) else "")

        print(f"Barcelona finished matches: {len(barca_matches)}")
        print(f"Barcelona ID: {BARCELONA_ID}\n")

        szcz_starters = 0
        szcz_bench = 0

        for match in barca_matches:  # ALL matches
            event_id = match.get("id")
            home = match.get("home", {})
            away = match.get("away", {})
            # Fix: compare as strings since home.get("id") returns string
            is_home = str(home.get("id")) == str(BARCELONA_ID)
            date_str = match.get("status", {}).get("utcTime", "???") if isinstance(match.get("status"), dict) else "???"

            # Get Barcelona lineup
            endpoint = "football-get-hometeam-lineup" if is_home else "football-get-awayteam-lineup"

            try:
                response = await client.get(
                    f"https://{API_HOST}/{endpoint}",
                    headers=headers,
                    params={"eventid": event_id},
                )
                lineup_data = response.json()

                # Debug: check full response structure
                lineup = lineup_data.get("response", {}).get("lineup", {})

                # Check ALL players for Barcelona IDs
                starters = lineup.get("starters", [])
                subs = lineup.get("subs", [])
                all_players = starters + subs

                # Check if ANY player has Barcelona ID (8634) in their team info
                # or check player IDs - Joan Garcia = 1167220, Szczesny = 169718
                barca_player_ids = [1167220, 169718]  # Joan Garcia, Szczesny

                has_barca_player = any(p.get("id") in barca_player_ids for p in all_players)

                # Find GK (usually position "GK" or first in list)
                gk = None
                for p in starters:
                    if p.get("position") == "GK":
                        gk = p
                        break

                if not gk and starters:
                    gk = starters[0]  # Assume first is GK

                gk_name = gk.get("name", "???") if gk else "NOT FOUND"
                gk_id = gk.get("id", "???") if gk else "???"

                # Check if Szczesny is in lineup (starters or subs)
                szcz_in_starters = any(p.get("id") == SZCZESNY_ID for p in starters)
                szcz_in_subs = any(p.get("id") == SZCZESNY_ID for p in subs)

                szcz_status = ""
                if szcz_in_starters:
                    szcz_status = " [SZCZESNY IN STARTERS]"
                elif szcz_in_subs:
                    szcz_status = " [SZCZESNY ON BENCH]"

                is_barca_lineup = "[BARCA]" if has_barca_player else "[OPPONENT]"

                # Count Szczesny appearances
                if szcz_in_starters:
                    szcz_starters += 1
                elif szcz_in_subs:
                    szcz_bench += 1

                # Debug: show home.id and away.id
                barca_str = "HOME" if is_home else "AWAY"
                print(f"{date_str[:10]} | home.id={home.get('id')} away.id={away.get('id')} | Barca: {barca_str} | {is_barca_lineup}")
                print(f"  {home.get('name')} {home.get('score')} - {away.get('score')} {away.get('name')}")
                print(f"  GK: {gk_name} (ID: {gk_id}){szcz_status}")

                await asyncio.sleep(0.05)

            except Exception as e:
                print(f"[!] Error: {e}")

        print("\n" + "=" * 60)
        print("SZCZESNY SUMMARY (La Liga)")
        print("=" * 60)
        print(f"In STARTERS: {szcz_starters}")
        print(f"On BENCH: {szcz_bench}")
        print(f"Total in squad: {szcz_starters + szcz_bench}")

        # Now collect GK stats for matches where Szczesny started
        print("\n" + "=" * 60)
        print("SZCZESNY GK STATS (La Liga - matches started)")
        print("=" * 60)

        total_stats = {
            "matches": 0,
            "minutes": 0,
            "clean_sheets": 0,
            "goals_conceded": 0,
            "shots_on_target_faced": 0,
            "saves": 0,
        }

        for match in barca_matches:
            event_id = match.get("id")
            home = match.get("home", {})
            away = match.get("away", {})
            is_home = str(home.get("id")) == str(BARCELONA_ID)
            date_str = match.get("status", {}).get("utcTime", "???") if isinstance(match.get("status"), dict) else "???"

            # Get Barcelona lineup
            endpoint = "football-get-hometeam-lineup" if is_home else "football-get-awayteam-lineup"

            try:
                response = await client.get(
                    f"https://{API_HOST}/{endpoint}",
                    headers=headers,
                    params={"eventid": event_id},
                )
                lineup_data = response.json()
                lineup = lineup_data.get("response", {}).get("lineup", {})
                starters = lineup.get("starters", [])

                # Check if Szczesny is in starters
                szcz_in_starters = any(p.get("id") == SZCZESNY_ID for p in starters)

                if not szcz_in_starters:
                    continue  # Skip matches where Szczesny didn't start

                # Get match stats
                response = await client.get(
                    f"https://{API_HOST}/football-get-match-all-stats",
                    headers=headers,
                    params={"eventid": event_id},
                )
                stats_data = response.json()
                stats = stats_data.get("response", {}).get("stats", [])

                # Team index: 0 = home, 1 = away
                team_idx = 0 if is_home else 1
                opp_idx = 1 if is_home else 0

                goals_conceded = away.get("score") if is_home else home.get("score")
                is_clean_sheet = goals_conceded == 0

                # Find ShotsOnTarget and keeper_saves
                shots_on_target = None
                keeper_saves = None

                for stat_group in stats:
                    for stat in stat_group.get("stats", []):
                        if stat.get("key") == "ShotsOnTarget":
                            shots_on_target = stat.get("stats", [None, None])
                        if stat.get("key") == "keeper_saves":
                            keeper_saves = stat.get("stats", [None, None])

                # Opponent shots on target (what Szczesny faced)
                opp_sot = shots_on_target[opp_idx] if shots_on_target else None
                # Szczesny's saves
                szcz_saves = keeper_saves[team_idx] if keeper_saves else None

                # Calculate save percentage
                if opp_sot and szcz_saves and opp_sot > 0:
                    save_pct = round((szcz_saves / opp_sot) * 100, 1)
                else:
                    save_pct = None

                total_stats["matches"] += 1
                total_stats["minutes"] += 90
                if is_clean_sheet:
                    total_stats["clean_sheets"] += 1
                total_stats["goals_conceded"] += goals_conceded
                if opp_sot:
                    total_stats["shots_on_target_faced"] += opp_sot
                if szcz_saves:
                    total_stats["saves"] += szcz_saves

                match_str = f"{home.get('name')} {home.get('score')} - {away.get('score')} {away.get('name')}"
                print(f"{date_str[:10]} | {match_str}")
                print(f"  GC: {goals_conceded} | CS: {is_clean_sheet} | SOT: {opp_sot} | Saves: {szcz_saves} | Save%: {save_pct}")

                await asyncio.sleep(0.05)

            except Exception as e:
                print(f"[!] Error: {e}")

        # Print summary
        print("\n" + "=" * 60)
        print("SZCZESNY SEASON STATS (La Liga - matches started)")
        print("=" * 60)
        print(f"Matches: {total_stats['matches']}")
        print(f"Minutes: {total_stats['minutes']}")
        print(f"Clean Sheets: {total_stats['clean_sheets']} ({round(total_stats['clean_sheets']/total_stats['matches']*100, 1) if total_stats['matches'] > 0 else 0}%)")
        print(f"Goals Conceded: {total_stats['goals_conceded']} ({round(total_stats['goals_conceded']/total_stats['matches'], 2) if total_stats['matches'] > 0 else 0}/match)")
        print(f"Shots on Target Faced: {total_stats['shots_on_target_faced']}")
        print(f"Saves: {total_stats['saves']}")
        if total_stats['shots_on_target_faced'] > 0:
            print(f"Save%: {round(total_stats['saves']/total_stats['shots_on_target_faced']*100, 1)}%")


if __name__ == "__main__":
    # asyncio.run(test_endpoints())
    # asyncio.run(find_szczesny_matches())
    asyncio.run(check_all_barca_keepers())
