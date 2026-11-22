# Pokémon Team Builder

**Live site:** https://pokemon-team-builder-c97p.onrender.com · **Setup:** [SETUP.md](SETUP.md) · **Demo:** [DEMO.md](DEMO.md) · **Security:** [SECURITY.md](SECURITY.md)

FastAPI, Postgres and React in one Docker image on Render; GitHub Actions schedules the scan.

## Key decisions

**A stored copy of PokéAPI, not a live proxy.** A scan reads PokéAPI four requests at a time, storing 13 fields per Pokémon and the 18 × 18 type chart. A proxy would call PokéAPI on every page load and keep nothing to compare.

**All 1,351 Pokémon.** The grid shows every PokéAPI entry; a checkbox hides Mega and regional forms. Counters come only from the 1,025 default forms; battle-only forms would win.

**Order is stored as slots.** A member is a row (team, position 1–6, Pokémon). Each edit sends the whole ordered list, rewritten in one transaction, so one Pokémon may fill several slots. Separate add, remove and move calls would be three paths to validate.

**Accounts are optional.** A visitor starts as a random HttpOnly, Secure, SameSite=Lax cookie, stored only as its SHA-256; clearing it loses the teams. An account adds a username and an Argon2id password hash, no email, so a lost password cannot be reset, and its owner can delete it; signing in merges that browser's teams, up to 20. Render's request log alone keeps IP addresses, briefly.

**The counter team.** Each opponent gets one designated counter; teams are compared on three levels in order: assigned matchup points (a point per doubling of damage dealt, minus one per doubling taken), then coverage (that score against every opponent, summed), then base stats. Every counter must hit its opponent super-effectively, none repeats, and no opposing type may hit more than half the team super-effectively, loosened, visibly, only if needed. A weighted blend would be arbitrary.

The search is exact over the pool in use: 1,025, or 931 with the filter. The last rule sees only a candidate's weakness pattern, so keeping each slot's n best per pattern cannot lose the best team: every unkept pick has a kept twin scoring no worse. Tests check it against brute force. A limit of 250,000 steps per strictness level bounds each request; no trial team, of 5,251 in either pool, reached it. Moves are left out. With every Pokémon allowed, 42.0% of picks on random teams are legendary or mythical by PokéAPI's flags; a checkbox leaves them out at about 0.05 matchup points per counter (3.029 to 2.981), and about 6% of picks still have a stat total of 600 or more.

**Change detection.** Each scan diffs every stored field and chart cell, recording old and new values. Failures never record one, and a Pokémon PokéAPI drops is flagged, not deleted. A change involves you if it touches a Pokémon on your teams now, or one of its types. Alerts cover seven days and can be dismissed. Per-user alerts written at scan time were rejected: they go stale.

**Staying up under load.** Four reused database connections and at most two counter searches at once; `make burst` checks a read burst ends in 429s.

**The demo** feeds altered PokéAPI answers into the real scan; reset restores the data.

## Known limits

- GitHub Actions schedules are best effort.
- While a demo is active, every visitor sees its values.
- No migration tool: tables change by hand.
- Two tabs on one team: last save wins.
- At most 10 new visitors a minute and 50,000 in all; beyond, newcomers cannot save until some are deleted by hand.
- Passwords need only 8 characters (OWASP asks 15); sessions last 30 days; blocking a username takes ten or more addresses.
