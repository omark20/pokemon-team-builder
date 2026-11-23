# Design notes

The README is the one page summary. This file holds the sources, the measurements and the ideas that were tried and dropped.

## Where the fight model comes from

The damage formula is the one the games use. It was taken from the open source Smogon damage calculator, which is under the MIT licence.

Every Pokémon fights at level 50, the level official competitive battles use. With no training, HP is the base stat plus 60 and every other stat is the base stat plus 5. The damage of one hit is `22 × power × attack ÷ defence ÷ 50 + 2`. It is half as much again when the move shares a type with its user, and is then multiplied for type.

PokéAPI has no field that says a move has a catch. So the app reads each move's short description and leaves out moves that charge, recharge, need a condition or faint their user. That removes 39 moves and leaves 533. A few slip through because their text does not mention the catch, such as Misty Explosion.

## Why the search is exact

Giving one different counter to each of your Pokémon is the classic assignment problem. Each slot keeps only its best few candidates, as many as the team has members. That loses nothing. If the best team used a candidate that was not kept, a kept candidate for that slot would still be free, and it scores at least as well.

The tests check this too. On small pools they build every possible team at sizes 1 to 6 and compare.

A second exact search keeps the team from sharing one weakness. It stops at 100,000 steps, and the first answer then stands with a notice on the page.

## What was measured

The trial used 5,251 generated teams. That is 3,000 random teams of one to six Pokémon, 900 teams of six that share a type, and one team of six copies for each of the 1,351 Pokémon. It was run while the model was being designed.

| Measure | Result |
|---|---|
| Counters that win their own fight | 99.9% |
| Different Pokémon picked | 660 |
| Picks that are legendary or mythical | 44% |
| Teams that need the second search | about 1 in 18 |
| Most steps the second search took in 40,000 random teams | 10,624, with a limit of 100,000 |
| Time for one counter team on the live server | half a second to a second |

## What was tried and dropped

| Idea | Why it was dropped |
|---|---|
| Rank counters by strength alone | The same few giants answered every team. 69% of picks were legendary. |
| Let each Pokémon use every move it can learn | Worse again, with 83% legendary. Four moves is also the games' own rule. |
| Rank first by how well a counter fits your team | Tiny Pokémon that barely win were picked. Fit works as the second step. |
| Type matchups only, with no moves | It was the first version. It could not tell a Pokémon with the right type from one that can actually win. |

## Decisions not in the README

| Decision | Instead of | Why |
|---|---|---|
| Start as an anonymous cookie | Forcing sign up | A visitor can build a team in seconds. |
| Unique team names enforced by the database | A check in code | No code path can forget the rule. |
| One web process | Several | Rate limits and the list cache live in memory, so one process keeps them exact. |
| The demo changes what the scan reads | Editing stored data directly | The real scan and the real alerts are what get shown. |
