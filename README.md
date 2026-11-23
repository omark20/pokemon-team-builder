# Pokémon Team Builder

**Live site:** https://pokemon-team-builder-c97p.onrender.com · **Setup:** [SETUP.md](SETUP.md) · **Demo:** [DEMO.md](DEMO.md) · **Security:** [SECURITY.md](SECURITY.md)

FastAPI, Postgres and React in one Docker image on Render. GitHub Actions requests a scan every six hours; the app also scans when the last is over seven hours old.

## Key decisions

**A stored copy of PokéAPI, not a live proxy.** A scan reads PokéAPI four requests at a time, storing 13 fields and the move list per Pokémon, every move, and the 18 × 18 type chart. A proxy would call PokéAPI on every page load and keep nothing to compare.

**All 1,351 Pokémon.** The grid shows every PokéAPI entry; a checkbox hides Mega and regional forms. Counters come only from the 1,025 default forms; battle-only forms would win.

**Order is stored as slots.** A member is a row (team, position 1–6, Pokémon). Each edit sends the whole ordered list, rewritten in one transaction, so one Pokémon may fill several slots. Separate add, remove and move calls would be three paths to validate.

**Accounts are optional.** A visitor starts as a random cookie, stored only as its SHA-256; clearing it loses the teams. An account adds a username and an Argon2id password hash, no email, so a lost password cannot be reset, and its owner can delete it; signing in merges that browser's teams, up to 20.

**The counter team.** Each of your Pokémon gets a counter that knocks it out first, one on one at level 50, by the games' damage formula (from Smogon's calculator). Each Pokémon carries the four of its PokéAPI moves that together hit the most Pokémon hardest. Counters rank in order (a weighted blend would be arbitrary): how decisively they win, then how much better they do against your team than against Pokémon in general (else most teams got the same giants), then base stats. Each must hit its opponent super-effectively, none repeats, and no opposing type may hit over half the team that hard.

The team is an exact assignment (931 candidates with the legendary checkbox). A second exact search keeps the type rule when that team breaks it, loosening it visibly only if no team can; past 100,000 steps the first team stands, with a notice. Tests compare both with every possible team, sizes 1 to 6.

**Assumed:** no training, full damage roll, no critical hits; the best of four moves every turn, misses as average damage; no abilities, items, weather, status moves, stat changes, priority or switching. Moves whose text says they charge, recharge, need a condition or faint the user are left out; recent textless moves slip through, as does `misty-explosion`, whose user also faints.

**Change detection.** Each scan diffs every stored field and chart cell, recording old and new values. Failures never record one, and a Pokémon PokéAPI drops is flagged, not deleted. A change involves you if it touches a Pokémon on your teams, or one of its types. Alerts cover seven days and can be dismissed. Per-user alerts written at scan time were rejected: they go stale.

**The demo** alters PokéAPI's answers and runs the real scan; reset restores the data.

## Known limits

- While a demo is active, every visitor sees its values.
- Two tabs on one team: last save wins.
- At most 10 new visitors a minute and 50,000 in all; beyond, newcomers cannot save until some are deleted by hand.
- Passwords need only 8 characters (OWASP asks 15); blocking a username takes ten or more addresses.
- No abilities: some picks look stronger than they are (Slaking); a narrow winner may be modest.
