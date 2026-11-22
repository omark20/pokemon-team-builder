# Pokémon Team Builder

**Live site:** https://pokemon-team-builder-c97p.onrender.com · **Setup:** [SETUP.md](SETUP.md) · **Demo:** [DEMO.md](DEMO.md)

FastAPI, Postgres and React in one Docker image on Render; a GitHub Actions schedule runs the scan.

## Key decisions

**A stored copy of PokéAPI, not a live proxy.** A server-side scan reads PokéAPI four requests at a time and stores 13 fields per Pokémon and the 18 × 18 type chart. A proxy would put PokéAPI on every page load, leaving nothing to compare against.

**All 1,351 Pokémon.** The grid shows all of PokéAPI's entries; a checkbox hides Mega and regional forms. Counters come only from the 1,025 default forms, or battle-only forms would win.

**Order is stored as slots.** A member is a row (team, position 1–6, Pokémon). Each edit sends the whole ordered list, rewritten in one transaction, so one Pokémon may fill several slots. Separate add, remove and move calls were rejected as three paths to validate.

**A user is an anonymous cookie.** A random HttpOnly, Secure, SameSite=Lax cookie, of which the database keeps only a SHA-256 hash. Clearing cookies loses the teams. No personal data is stored; only Render's request log keeps IP addresses, for a limited time.

**The counter team.** Each opponent gets one designated counter; teams are compared on three levels in order: assigned matchup points (a point per doubling of damage dealt, minus one per doubling taken), then coverage (that score against every opponent, summed), then base stats. Every counter must hit its opponent super-effectively, none repeats, and no opposing type may hit more than half the team super-effectively, loosened, visibly, only if no team can meet it. A weighted blend was rejected: its weights would be arbitrary.

The search is exact over the pool in use: 1,025, or 931 with the filter. The last rule sees only a candidate's weakness pattern, so keeping each slot's n best per pattern cannot lose the best team: an unkept pick can be swapped for a kept one of the same pattern that scores no worse. Tests check it against brute force. A limit of 250,000 steps per strictness level bounds each request; no trial team, of 5,251 in either pool, reached it. Moves and damage formulas are left out. With every Pokémon allowed, about four picks in ten are legendary or mythical by PokéAPI's own flags (42.0% on random teams); a checkbox leaves them out at about 0.05 matchup points per counter (3.029 to 2.981), and about 6% of picks still have a stat total of 600 or more.

**Change detection.** Each scan diffs every stored field and chart cell, recording old and new value, Pokémon and time. Failures never record one, and a Pokémon PokéAPI drops is flagged, not deleted. A change involves you if the Pokémon is on one of your teams now, or a changed chart cell names one of its types. Alerts cover seven days and can be dismissed. Per-user alerts written at scan time were rejected: they go stale as teams change.

**Staying up under load.** Requests share four connections opened at start-up, and at most two counter searches run at once; a connection per request let a read burst exhaust the small database before any rate limit applied. `make burst` checks that one now ends in 429s.

**The demo** feeds altered PokéAPI answers into the real scan, before the comparison; reset restores the data.

## Known limits

- GitHub Actions schedules are best effort.
- While a demo is active, every visitor sees its values.
- No migration tool: existing tables are changed by hand.
- Two tabs on one team: last save wins.
