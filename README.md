# Pokémon Team Builder

**Live site:** https://pokemon-team-builder-c97p.onrender.com · **Run it locally:** [SETUP.md](SETUP.md) · **Change-alert demo:** [DEMO.md](DEMO.md)

Build teams of up to six Pokémon, get a counter team for each, and be alerted when PokéAPI changes your Pokémon. FastAPI and Postgres behind a React page, in one Docker image on Render; a scheduled GitHub Actions job runs the scan.

## Key decisions

**A stored copy of PokéAPI, not a live proxy.** A server-side scan reads PokéAPI four requests at a time and stores ten values per Pokémon plus the 18 × 18 type chart. The grid is served from that copy. A proxy would put PokéAPI on every page load and leave nothing to compare a change against.

**All 1,351 Pokémon.** The grid shows every entry PokéAPI lists, with a checkbox to hide Mega and regional forms. Counters come from the 1,025 default forms only, or battle-only forms would win every answer.

**Order is stored as slots.** A member is a row (team, position 1–6, Pokémon). Every edit sends the whole ordered list, rewritten in one transaction, so positions never gap or clash and one Pokémon may fill several slots. Separate add, remove and move calls were rejected: three paths to validate instead of one.

**A user is an anonymous cookie.** No accounts: a random HttpOnly, Secure, SameSite=Lax cookie, of which the database keeps only a SHA-256 hash. Clearing cookies loses the teams. No personal data is stored; like any web host, Render's request log keeps IP addresses for a while, and the app copies them nowhere.

**The counter team.** Each opponent gets one designated counter. Teams are compared on three levels, strictly in order: assigned matchup points (a point per doubling of damage dealt, minus one per doubling taken), then coverage (that score against every opponent, summed), then base stats. Every counter must hit its opponent super-effectively, none appears twice, and no opposing type may hit more than half the team super-effectively; that rule is loosened only when no team meets it, and the page says so. A weighted blend was rejected: its weights could not be justified.

The search is exact over all 1,025 candidates. The last rule sees only a candidate's weakness pattern, so keeping each slot's n best per pattern cannot lose the best team: an unkept pick can be swapped for a kept one of the same pattern that scores no worse. Tests check it against brute force. A limit of 250,000 steps per strictness level bounds each request; 1,180 random and one-type trial teams never reached it. Moves and damage formulas are left out, and about a third of picks (33.6% on 1,000 random teams) are legendary-strength.

**Change detection.** Each scan compares every stored field and chart cell and records old value, new value, Pokémon and time per change. Failures never record one: an unreadable Pokémon is skipped, a bad list or chart leaves storage untouched, and a Pokémon PokéAPI drops is flagged, not deleted. A change involves you if the Pokémon is on one of your teams now, or a changed chart cell's attacking or defending type is one of your Pokémon's types. Alerts cover seven days and can be dismissed. Writing alerts per user at scan time was rejected: they go stale as teams change.

**The demo** makes the scan believe PokéAPI said something else, before the comparison, so the scheduled job's own path raises the alert; reset restores the data.

## Known limits

- GitHub Actions schedules are best effort.
- While a demo is active, every visitor sees its values.
- No migration tool: changes to existing tables are made by hand.
- Two tabs editing one team: the last save wins.
