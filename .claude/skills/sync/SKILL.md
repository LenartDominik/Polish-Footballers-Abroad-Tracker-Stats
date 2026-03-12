# Sync Player Data

Safe workflow for syncing player statistics from RapidAPI to Supabase.

## Steps

1. **DRY-RUN FIRST** - Always run with `--dry-run` flag:
   ```bash
   python scripts/sync_players.py --dry-run
   ```

2. **Review changes carefully** - Check output for:
   - Which players will be updated
   - What stats will change
   - Any players marked for deletion (STOP if you see this)

3. **NEVER delete existing data** - If API returns empty/error:
   - Keep existing player stats unchanged
   - Log the error and continue
   - Do NOT set values to 0 or NULL

4. **Run sync** (only if dry-run looks good):
   ```bash
   python scripts/sync_players.py
   ```

5. **Verify results** - Check database:
   ```bash
   python scripts/verify_sync.py
   ```

6. **Commit only after verification**

## Safety Rules

- Preserve existing `games` and `minutes_played` when only updating goals/assists/cards
- Use `upsert` not `replace` - update existing, insert new
- Log all changes to `sync_log` table
- Stop immediately if >10% of players would have stats decreased
