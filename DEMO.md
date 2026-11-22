# Change-alert demo

PokéAPI rarely changes, so the demo makes the scan believe it did. A stored patch replaces
what PokéAPI said for chosen Pokémon after each response is read and before it is compared
with the stored copy. Everything after that is the scheduled job's own code: the same
comparison, the same change records, the same alert query. Nothing writes an alert
directly. The example changes Charizard's attack from 84 to 94.

Locally, take the two tokens from your `.env` and use `http://127.0.0.1:8000` with
`make dev` running (see [SETUP.md](SETUP.md)). On the public site only the site's owner holds
`ADMIN_TOKEN`.

```bash
export APP_URL=http://127.0.0.1:8000
export SCAN_TOKEN=...   # from .env
export ADMIN_TOKEN=...  # from .env
```

1. **Baseline.** In the browser, add Charizard to a team. No alert is shown.

2. **Change upstream.** Store the patch. Refresh the page: still no alert, because
   nothing has been scanned.

   ```bash
   curl -X PUT "$APP_URL/api/admin/demo/overrides" \
     -H "Authorization: Bearer $ADMIN_TOKEN" -H "Content-Type: application/json" \
     -d '{"pokemon": {"6": {"attack": 94}}, "type_chart": []}'
   ```

3. **Run the job**, for Charizard only (a full run is the same command with no body). On the
   public site the scheduled workflow does the same: press "Run workflow" on the scan workflow
   in GitHub Actions.

   ```bash
   curl -X POST "$APP_URL/api/admin/scan" \
     -H "Authorization: Bearer $SCAN_TOKEN" -H "Content-Type: application/json" \
     -d '{"pokemon_ids": [6]}'
   ```

4. **See the alert.** Refresh: an alert shows Charizard's attack going from 84 to 94,
   tagged as demo data, and Charizard's card shows 94. A second browser profile whose team
   has no Charizard sees nothing.

5. **Reset.** This writes the original values back and removes the demo's change records.
   Run the scan of step 3 again: no alert, no new change.

   ```bash
   curl -X POST "$APP_URL/api/admin/demo/reset" -H "Authorization: Bearer $ADMIN_TOKEN"
   ```

`GET /api/scan/status` reports `"demo_active": true` from step 2 until the reset. The demo
endpoints refuse `SCAN_TOKEN`, so the scheduler's token cannot change data.

`make smoke` runs these same steps by script against a local setup and checks each result.
