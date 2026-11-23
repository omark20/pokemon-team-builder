# Pokémon Team Builder

[Live site](https://pokemon-team-builder-c97p.onrender.com) · [Setup](SETUP.md) · [Demo](DEMO.md) · [Demo video](https://pokemon-team-builder-c97p.onrender.com/change-alert-demo.mp4) · [Security](SECURITY.md) · [Design notes](DESIGN.md)

Build Pokémon teams, get the best counter team for each, and get an alert when PokéAPI changes something a team uses. It all runs as FastAPI, Postgres and React in one Docker image on Render.

## Key decisions

**A stored copy of PokéAPI, not a live proxy.** A scan reads PokéAPI and stores every Pokémon, every move and the type chart in Postgres. A proxy was rejected because it would depend on PokéAPI for every page and keep nothing to compare against. GitHub Actions asks for a scan every six hours, and the app starts one itself if that is skipped.

**A team remembers the order of its Pokémon.** Each Pokémon on a team is stored with its position from 1 to 6. Every edit sends the whole team in its new order, and the server replaces the old one in one database transaction. Separate calls to add, remove and move were rejected because they are three things to keep correct instead of one.

**Accounts are optional.** A visitor starts as a random cookie, and the server stores only its hash. An account adds a username and an Argon2id password hash, and signing in moves that browser's teams into it. No email is collected, so the app holds no contact details.

**The counter team.** For each of your Pokémon the app picks a counter that wins a one on one fight against it. The fight uses the games' own damage formula at level 50, taken from Smogon's calculator. Every Pokémon carries up to four moves, either the ones you choose or four the app picks one at a time to hit the most Pokémon hardest. Counters are ranked in order.

1. How clearly they win their own fight.
2. How much better they do against your team than against Pokémon in general. This stops the same few giants answering every team.
3. Base stats.

These stay as ordered steps because any weighted mix would be an invented number. Picking six different counters is a matching problem, and the app solves it exactly. Every counter must have a move that hits its opponent for double damage or more. A second exact search makes sure no type on your team hits more than half the counters that hard. If no team can do that, the limit rises by one and the page says so. Tests compare both searches with every possible team on small pools. In a trial of 5,251 generated teams, 99.9% of the counters picked won their fight.

**Change detection.** Each full scan compares every stored field, move and type chart cell with PokéAPI and records the old and new values. A failed request never records a change. A change involves you if it touches a Pokémon on your teams, one of its types or a move it carries. Alerts last seven days and can be dismissed. They are worked out when the page asks, because alerts stored per user would go stale when a team changes.

**The demo** changes what the scan reads from PokéAPI, then runs the real scan.

## Assumptions

- Counters come only from the 1,025 default forms, because forms that exist only in battle would always win.
- Each side uses the best of its four moves every turn. A move that can miss counts as its average damage.
- No training, critical hits, abilities, items, weather, status moves, stat changes, priority or switching.
- Moves whose description says they charge, recharge, need a condition or faint their user are left out. A few that do not say so slip through.

## Known limits

- A lost password cannot be reset, since no email is collected.
- The second search stops at 100,000 steps and then shows the first answer with a notice. No trial team came close.
- Without abilities some picks, such as Slaking, look stronger than they are.
- A Pokémon gaining or losing a move raises no alert.
