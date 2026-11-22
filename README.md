# Pokémon Team Builder

**Live site:** https://pokemon-team-builder-c97p.onrender.com · **Setup:** [SETUP.md](SETUP.md) · **Demo:** [DEMO.md](DEMO.md)

FastAPI, Postgres and React in one Docker image on Render; GitHub Actions runs the PokéAPI scan on a schedule.

## Key decisions

**A stored copy of PokéAPI, not a live proxy.** A server-side scan reads PokéAPI four requests at a time and stores 11 fields per Pokémon and the 18 × 18 type chart. A proxy would put PokéAPI on every page load and leave nothing to compare a change against.

**All 1,351 Pokémon.** The grid shows every entry PokéAPI lists; a checkbox hides Mega and regional forms. Counters come from the 1,025 default forms only, or battle-only forms would win every answer.

**Order is stored as slots.** A member is a row (team, position 1–6, Pokémon). Every edit sends the whole ordered list, rewritten in one transaction: no gaps or clashes, and one Pokémon may fill several slots. Separate add, remove and move calls were rejected: three paths to validate instead of one.

**A user is an anonymous cookie.** A random HttpOnly, Secure, SameSite=Lax cookie, of which the database keeps only a SHA-256 hash. Clearing cookies loses the teams. No personal data is stored; only Render's request log keeps IP addresses, for a limited time.

**The counter team.** Each opponent gets one designated counter, and teams are compared on three levels in order: assigned matchup points (a point per doubling of damage dealt, minus one per doubling taken), then coverage (that score against every opponent, summed), then base stats. Every counter must hit its opponent super-effectively, none appears twice, and no opposing type may hit more than half the team super-effectively; that rule is loosened only when no team meets it, and the page says so. A weighted blend was rejected: its weights would be arbitrary.

The search is exact over all 1,025 candidates. The last rule sees only a candidate's weakness pattern, so keeping each slot's n best per pattern cannot lose the best team: an unkept pick can be swapped for a kept one of the same pattern that scores no worse. Tests check it against brute force. A limit of 250,000 steps per strictness level bounds each request; 1,180 random and one-type trial teams never reached it. Moves and damage formulas are left out, and about a third of picks (33.6% on 1,000 random teams) are legendary-strength.

**Change detection.** Each scan diffs every stored field and chart cell, recording old and new value, Pokémon and time. A failure never records one: unreadable data is skipped and storage left untouched, and a Pokémon PokéAPI drops is flagged, not deleted. A change involves you if the Pokémon is on one of your teams now, or a changed chart cell's attacking or defending type is one of its types. Alerts cover seven days and can be dismissed. Writing alerts per user at scan time was rejected: they go stale as teams change.

**Staying up under load.** Requests share four connections opened at start-up, and at most two counter searches run at once; a connection per request let a read burst exhaust the small database before any rate limit applied. `make burst` checks that one now ends in 429s.

**The demo** feeds the scan altered PokéAPI answers before the comparison, so the scheduled job's own path raises the alert; reset restores the data.

## Known limits

- GitHub Actions schedules are best effort.
- While a demo is active, every visitor sees its values.
- No migration tool: existing tables are changed by hand.
- Two tabs editing one team: the last save wins.
