# Security

How the site protects its visitors, itself and its secrets: for each, the threat, what the app does, where, and the test that shows it (in `backend/tests/`).

## What there is to protect

Visitors' teams; the site staying up; the two admin tokens; the stored copy of PokéAPI, which only the scan and the demo may change.

## Who a visitor is

**Threat:** someone guesses or forges who they are. There are no accounts: a visitor is a cookie, `uid`, holding 32 random bytes (`secrets.token_urlsafe`), marked HttpOnly, Secure and SameSite=Lax, kept for a year (`auth.create_user`). The database stores only its SHA-256, so a copy of it gives no working cookie; a made-up cookie matches no one. No name, email or address is stored; Render's own request log records IP addresses for a limited time. *Tests:* `test_the_cookie_is_httponly_secure_and_samesite_lax`, `test_a_made_up_cookie_is_treated_as_none`.

## Your teams are yours

**Threat:** reading or changing another visitor's team. Every team request looks the team up together with the cookie's visitor (`routes/teams._owner`); another visitor's team answers 404, like one that does not exist. The browser never says who it is: bodies refuse unknown fields such as `user_id`. *Tests:* `test_another_visitors_team_is_404_for_every_verb`, `test_a_user_id_in_the_body_is_refused_and_in_the_query_ignored`.

## The admin endpoints

**Threat:** a stranger runs the scan or changes data. `SCAN_TOKEN` may only start a scan; `ADMIN_TOKEN` runs the demo controls. Each is compared in constant time (`auth._bearer_matches`). An unset or blank token keeps its endpoints closed, and the app refuses to start if the two are equal (`config.load_settings`). Admin calls are limited before the token check, and wrong tokens are logged once per address a minute. *Tests:* `test_each_admin_endpoint_opens_only_to_its_own_token`, `test_an_endpoint_whose_token_is_unset_stays_closed`, `test_the_two_tokens_must_differ`.

## Requests from other sites

**Threat:** another page makes a visitor's browser write here. A write whose `Origin` names another site is refused with 403 (`main.is_cross_site_write`); SameSite=Lax keeps the cookie off cross-site writes anyway. No GET request changes anything. *Test:* `test_write_from_another_site_is_refused`.

## What a request may contain

**Threat:** malformed or oversized input. Bodies are strict: exact types, no unknown fields, bounded lengths and IDs. A team name is 1 to 50 characters, with no control characters and at least one visible one. Bodies over 16 KB (64 KB for the demo document) are refused with 413 *while being read*, before parsing or any token check (`main.MAX_BODY_BYTES`). *Tests:* `test_malformed_requests_are_4xx_never_500`, `test_names_are_1_to_50_visible_characters_without_control_characters`, `test_an_oversized_body_is_refused_with_413_before_it_is_read`.

## Database safety

**Threat:** SQL injection. Every value is sent separately from the SQL. A column name is built in two places only, both from the app's own record fields through `psycopg.sql.Identifier`: the scan's column lists (`scan_store.py`) and demo reset, which refuses any other name (`demo._restore`). *Test:* `test_hostile_names_are_stored_and_returned_verbatim`.

## What the browser will run

**Threat:** script or framing injected into the page. The page shows names as text, never as HTML. Every response carries:

| Header | Value |
|---|---|
| Content-Security-Policy | `default-src 'self'`; images also from `raw.githubusercontent.com`; no framing |
| X-Content-Type-Options | nosniff |
| Referrer-Policy | no-referrer |
| X-Frame-Options | DENY |
| Strict-Transport-Security | one year |

The documentation routes are off and the server does not announce itself. *Tests:* `test_security_headers_on_every_response`, `test_documentation_routes_are_off`.

## Limits

**Threat:** a script floods the site or fills the database (`limits.LIMITS`, `auth.MAX_VISITORS`, `routes/counter.py`, `domain/counter_search.py`):

| What | Limit |
|---|---|
| Reads (every GET under `/api`) | 600 a minute per address |
| Writes | 120 a minute per address |
| Counter teams | 20 a minute per address; two searched at once; 250,000 steps per strictness level |
| New visitors | 20 an hour per address; 10 a minute from all addresses together |
| Visitors in all | 50,000 |
| Admin calls | 30 a minute per address |

Over a limit is 429 with `Retry-After`; the page says to try again in a few seconds or minutes. A visitor's address is the `CF-Connecting-IP` header Render's edge sets (`limits.client_address`): probing the live site, the edge refused a request that set it, while `X-Forwarded-For` began with whatever the sender wrote. *Tests:* `test_limits.py`.

## Staying up

**Threat:** a burst takes the site down. Requests share four database connections and wait at most two seconds for one, then get 503 with `Retry-After`; connecting gives up after five seconds (`db.py`). The health check needs no worker thread. `make burst` runs three checks against a database of the deployed size: 720 reads give 600 answers and 120 refusals; 3,000 from five addresses are all answered; a restarted database is answered again with no app restart. *Test:* `test_healthz_answers_while_every_worker_thread_is_busy`.

## Secrets

**Threat:** a token or database address leaks. Secrets live only in the host's environment and, locally, in a git-ignored `.env`; `.env.example` holds placeholders. The image copies only the app and the built page. The scheduled workflow has no repository permissions (`permissions: {}`) and passes `SCAN_TOKEN` from GitHub's secret store in a header.

## Logs

**Threat:** a secret or visitor detail written to the log. Lines carry named fields only; outside text is quoted so it cannot start a new line; exceptions are logged by class and code location, never by message (`logs.py`). The app's own lines never carry tokens, cookies, bodies, connection strings or visitor addresses; the web server's access line shows only the address of Render's proxy; and the database library's routine and warning messages are silenced. *Tests:* `test_no_secret_cookie_or_request_body_reaches_the_log`, `test_only_the_helper_logs_exceptions`.

## The scan

**Threat:** bad upstream data corrupts the copy. Only PokéAPI's host is fetched, redirects are not followed, and every response passes a strict parser (`pokeapi.py`, `domain/diff.py`). A failure skips that Pokémon and records no change; a list that looks truncated stops the run before anything is changed (`scan.py`); more than 20 disappearances in one run removes none of them and marks the run incomplete (`scan_store.apply_removals`). *Tests:* `test_scan.py`, `test_pokeapi.py`.

## The demo

Admin only. Its changes are tagged and reset removes exactly them; both controls answer 409 while a scan runs (`demo.py`). *Tests:* `test_admin_api.py`.

## Dependencies

`make audit` runs `pip-audit` over every locked backend package and `npm audit` over the page's: no known vulnerabilities on 2026-11-22.

## What is not protected

- No accounts: losing the cookie loses the teams, and anyone holding the cookie holds them.
- Someone with many addresses can slow first-time visitors and, over days, reach the visitor ceiling.
- While a demo is active, every visitor sees its values.
- The schedule is best effort.
- Trusting `CF-Connecting-IP` rests on the host's observed behaviour, not a documented promise.
