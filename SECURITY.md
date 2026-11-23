# Security

How the site protects its visitors, itself and its secrets: for each, the threat, what the app does, where, and the test that shows it (in `backend/tests/`).

## What there is to protect

Visitors' teams; the site staying up; the two admin tokens; the stored copy of PokéAPI, which only the scan and the demo may change.

## Who a visitor is

**Threat:** someone guesses or forges who they are. A visitor is a cookie, `uid`, holding 32 random bytes (`secrets.token_urlsafe`), marked HttpOnly, Secure and SameSite=Lax. It holds either an anonymous visitor's token, kept for a year (`auth.create_user`), or a signed-in browser's session token, good for 30 days from sign-in and checked on the server (`auth.identify`). The database stores only each token's SHA-256, so a copy of it gives no working cookie; a made-up or expired cookie matches no one. Every sign-up and sign-in issues a new token and destroys the one it replaces. The cookie is Secure everywhere except in answers to a request whose `Host` header names this computer (`localhost`, `127.0.0.1` or `[::1]`), because Safari refuses a Secure cookie over `http://localhost` (`auth.cookie_is_secure`). A visitor of the public site cannot use that against anyone: the attribute is set by the answer to the very request that carries the header, so forging it changes only the forger's own cookie. An anonymous visitor's record holds nothing about a person; an account adds only the username chosen and a password hash, never an email. Render's own request log records IP addresses for a limited time. *Tests:* `test_the_cookie_is_httponly_secure_and_samesite_lax`, `test_the_cookie_is_secure_except_for_a_request_to_this_computer`, `test_a_made_up_cookie_is_treated_as_none`, `test_a_session_lasts_30_days`, `test_an_anonymous_visitor_keeps_their_teams_and_gets_a_new_cookie`.

## Accounts and passwords

**Threat:** a password is guessed, read or leaked, or one account reaches another. Accounts are optional: a username and a password, no email (`accounts.py`, `account_store.py`, `routes/sessions.py`).

- A username is 3 to 20 of the letters a to z in either case, digits, `_`, `-` and `.`, and is unique whatever its capitals. A password is 8 to 128 characters of any kind and is never trimmed; one of 46,483 common passwords (SecLists' NCSC list, compared in lower case), or the username itself, is refused.
- Passwords are hashed with Argon2id at OWASP's setting of 19 MiB, 2 passes and 1 lane; the stored string carries its salt and settings. At most two hashes are worked out at once, then 503; no database connection is held while hashing.
- An unknown name and a wrong password get the same 401 and the same body after the same work: for an unknown name a fixed dummy hash is verified.
- Signing in merges the browser's anonymous teams into the account, oldest first, up to 20, in one transaction; the rest are deleted with the browser's record, and the sign-in form says so first. Nothing is merged from a browser signed in to another account.
- An account has at most 10 sessions, the oldest removed first; signing out deletes that browser's session on the server. Its owner can delete an account with its current password: the account, its teams, its dismissals and every session go together, so every device is signed out, and the name is free again.
- The password is a secret type from the moment the body is read, and no validation error quotes what was sent (`main.validation_failed`).

*Tests:* `test_accounts.py`, `test_accounts_api.py`.

## Your teams are yours

**Threat:** reading or changing another visitor's team. Every team request looks the team up together with the cookie's visitor (`routes/teams._owner`); another visitor's team answers 404, like one that does not exist. The browser never says who it is: bodies refuse unknown fields such as `user_id`. *Tests:* `test_another_visitors_team_is_404_for_every_verb`, `test_a_user_id_in_the_body_is_refused_and_in_the_query_ignored`.

## The admin endpoints

**Threat:** a stranger runs the scan or changes data. `SCAN_TOKEN` may only start a scan; `ADMIN_TOKEN` runs the demo controls. Each is compared in constant time (`auth._bearer_matches`). An unset or blank token keeps its endpoints closed, and the app refuses to start if the two are equal (`config.load_settings`). Admin calls are limited before the token check, and wrong tokens are logged once per address a minute. *Tests:* `test_each_admin_endpoint_opens_only_to_its_own_token`, `test_an_endpoint_whose_token_is_unset_stays_closed`, `test_the_two_tokens_must_differ`.

## Requests from other sites

**Threat:** another page makes a visitor's browser write here. A write whose `Origin` names another site, or `null`, is refused with 403 (`main.is_cross_site_write`); SameSite=Lax keeps the cookie off cross-site writes anyway. This covers sign-up, sign-in and sign-out as well, so another page cannot sign a visitor in to someone else's account. No GET request changes anything. *Tests:* `test_write_from_another_site_is_refused`, `test_a_sign_in_sent_as_a_form_from_another_site_is_refused`.

## What a request may contain

**Threat:** malformed or oversized input. Bodies are strict: exact types, no unknown fields, bounded lengths and IDs. A team name is 1 to 50 characters, with no control characters and at least one visible one. Bodies over 16 KB (64 KB for the demo document) are refused with 413 *while being read*, before parsing or any token check (`main.MAX_BODY_BYTES`). A 422 names each problem's kind and place, never the value sent. *Tests:* `test_malformed_requests_are_4xx_never_500`, `test_names_are_1_to_50_visible_characters_without_control_characters`, `test_an_oversized_body_is_refused_with_413_before_it_is_read`, `test_a_malformed_body_is_422_without_its_password`.

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

**Threat:** a script floods the site, fills the database or guesses passwords (`limits.LIMITS`, `auth.MAX_VISITORS`, `routes/counter.py`, `domain/counter_search.py`, `routes/sessions.py`):

| What | Limit |
|---|---|
| Reads (every GET under `/api`) | 600 a minute per address |
| Writes | 120 a minute per address |
| Counter teams | 20 a minute per address; two searched at once. The search is exact with no step limit (for six opponents, at most 36 kept candidates and 720 ways to hand them out); a second search, run only when the best team breaks the shared-weakness rule, stops at 100,000 steps and then answers with the first search's team and a notice |
| New visitors | 20 an hour per address; 10 a minute from all addresses together |
| Visitors in all, accounts included | 50,000 |
| Sign-in attempts, real names or not, successes included | 10 in 15 minutes for one username from one address; 20 in 15 minutes from one address, whatever the names; 100 in 15 minutes for one username from all addresses together |
| Account deletions | 5 in 15 minutes from one signed-in browser, within its address's 20; never counted per username, so strangers cannot use them up |
| Account-creation attempts | 5 an hour per address, taken names included; 60 an hour from all addresses together |
| Password hashes at once | 2 |
| Admin calls | 30 a minute per address |

Over a limit is 429 with `Retry-After`; the page says to try again in a few seconds or minutes. A visitor's address is the `CF-Connecting-IP` header Render's edge sets (`limits.client_address`): probing the live site, the edge refused a request that set it, while `X-Forwarded-For` began with whatever the sender wrote. *Tests:* `test_limits.py`.

## Staying up

**Threat:** a burst takes the site down. Requests share four database connections and wait at most two seconds for one, then get 503 with `Retry-After`; connecting gives up after five seconds (`db.py`). The health check needs no worker thread. `make burst` runs three checks against a database of the deployed size: 720 reads give 600 answers and 120 refusals; 3,000 from five addresses are all answered; a restarted database is answered again with no app restart. *Test:* `test_healthz_answers_while_every_worker_thread_is_busy`.

## Secrets

**Threat:** a token or database address leaks. Secrets live only in the host's environment and, locally, in a git-ignored `.env`; `.env.example` holds placeholders. The image copies only the app and the built page. The scheduled workflow has no repository permissions (`permissions: {}`) and passes `SCAN_TOKEN` from GitHub's secret store in a header.

## Logs

**Threat:** a secret or visitor detail written to the log. Lines carry named fields only; outside text is quoted so it cannot start a new line; exceptions are logged by class and code location, never by message (`logs.py`). The app's own lines never carry tokens, cookies, bodies, connection strings or visitor addresses. Account events (created, signed in, sign-in failed, signed out, deleted) carry only the request ID and the account's internal number: never a username, since people sometimes type their password into that box, nor a password, a hash or a token; the web server's access line shows only the address of Render's proxy; and the database library's routine and warning messages are silenced. *Tests:* `test_no_secret_cookie_or_request_body_reaches_the_log`, `test_account_flows_log_no_username_password_hash_or_cookie`, `test_only_the_helper_logs_exceptions`.

## The scan

**Threat:** bad upstream data corrupts the copy. Only PokéAPI's host is fetched, redirects are not followed, and every response passes a strict parser (`pokeapi.py`, `domain/diff.py`). A failure skips that Pokémon and records no change; a list that looks truncated stops the run before any Pokémon is changed (`scan.py`); more than 20 disappearances in one run removes none of them and marks the run incomplete (`scan_store.apply_removals`). *Tests:* `test_scan.py`, `test_pokeapi.py`.

## The demo

Admin only. Its changes are tagged and reset removes exactly them; both controls answer 409 while a scan runs (`demo.py`). *Tests:* `test_admin_api.py`.

## Dependencies

`make audit` runs `pip-audit` over every locked backend package and `npm audit` over the page's: no known vulnerabilities on 2026-11-22.

## What is not protected

- Without an account, losing the cookie loses the teams; with or without one, anyone holding the cookie holds them until it ends.
- Passwords need only 8 characters. OWASP calls fewer than 15 weak where there is no second factor, and there is none.
- There is no email and no password reset: a forgotten password loses the account. A password cannot be changed; its owner can delete the account and make a new one.
- A session lasts 30 days with no time-out for inactivity. A password cannot be changed and there is no "sign out everywhere", so a leaked password or a stolen session can be stopped only by deleting the account.
- Sign-up says when a name is taken, so names can be tested, 5 an hour per address.
- Against one username, one address can try 960 passwords a day, and ten or more addresses together 9,600. Keeping its owner from signing in takes ten or more addresses sending 100 attempts between them every quarter of an hour, without a pause; a ceiling of 50 would have taken only two, which is why it is 100. Nobody at another address can block the owner from deleting the account. These counts rest on the visitor's address (`limits.client_address`); if that header could be faked, only the 100 per username would still hold.
- There is no anti-forgery token: requests from other sites are stopped by the `Origin` check and SameSite only, two layers where OWASP also recommends a token.
- Stored hashes are not upgraded if the hash settings change, and the cookie does not use the `__Host-` name prefix.
- Someone with many addresses can slow first-time visitors and, over days, reach the visitor ceiling.
- While a demo is active, every visitor sees its values.
- The schedule is best effort.
- Trusting `CF-Connecting-IP` rests on the host's observed behaviour, not a documented promise.
