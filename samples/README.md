# Captured PokéAPI samples

Raw responses captured 2026-11-19 (UTC 2026-11-20 02:20) with plain `curl`, unmodified.
The app's response parser and its tests are written from these files.

| File | Request |
|---|---|
| `pokemon_list_limit20.json` | `GET /pokemon?limit=20` |
| `pokemon_list_full.json` | `GET /pokemon?limit=100000` |
| `pokemon_25_pikachu_single_type.json` | `GET /pokemon/25` |
| `pokemon_6_charizard_dual_type.json` | `GET /pokemon/6` |
| `pokemon_10034_nondefault_form.json` | `GET /pokemon/10034` |
| `type_10_fire.json` | `GET /type/10` |
| `type_list.json` | `GET /type?limit=100` |
| `headers_pokemon_6.txt` | response headers of `GET /pokemon/6` |

## Facts verified by these captures

1. **The list endpoint returns 1351 entries, not ~1025.** IDs 1–1025 are default
   Pokémon; IDs 10001–10326 (326 entries) are alternate forms such as
   `charizard-mega-x`. Alternate forms have `is_default: false` and their own
   types and stats (Charizard is fire/flying; Mega X is fire/dragon).
2. **List entries carry only `name` and `url`.** Types, stats and sprite need the
   detail endpoint. Pagination is `limit`/`offset` with a `next` URL; one call with
   a large `limit` returns everything.
3. **Detail payloads are large: 143 KB to 424 KB each.** The `moves` array is most
   of it (110–132 entries, each with `version_group_details`). A full sync of all
   1351 is therefore on the order of 400 MB of JSON (estimate from three samples).
4. **Types are an array of `{slot, type: {name, url}}`**, one or two entries.
5. **Stats are always these six**, in this order: `hp`, `attack`, `defense`,
   `special-attack`, `special-defense`, `speed`, each with `base_stat` and `effort`.
6. **`/type` returns 21 types, not 18.** The extra three are `stellar`, `unknown`
   and `shadow`; only the 18 standard types are used.
7. **Type effectiveness is in `/type/{id}` under `damage_relations`** with six
   lists: `double_damage_to`, `half_damage_to`, `no_damage_to`,
   `double_damage_from`, `half_damage_from`, `no_damage_from`. Anything not listed
   is neutral (1×). There is also a `past_damage_relations` field.
8. **Sprites are URLs on `raw.githubusercontent.com`**, not on pokeapi.co.
9. **Response headers include** `cache-control: public, max-age=86400`, a weak
   `etag`, `x-pokeapi-hash`, and `x-pokeapi-deploy-date` (epoch seconds), and
   `access-control-allow-origin: *`.

## Added 2026-11-20 (about 22:25–22:30 UTC)

Raw bodies below were fetched with `curl -s --compressed` and saved unmodified.

| File | Request |
|---|---|
| `type_{1..18}_{name}.json` (17 new; `type_10_fire.json` re-fetched and byte-identical) | `GET /type/{id}` for the 18 standard types |
| `type_19_stellar.json`, `type_10001_unknown.json`, `type_10002_shadow.json` | `GET /type/{id}` for the three non-standard types |
| `pokemon_10264_null_sprite.json` | `GET /pokemon/10264` (`koraidon-limited-build`) |
| `pokemon_{3,9,34,59,76,130,131,135,149,248}_{name}.json` | `GET /pokemon/{id}` for the Pokémon used in the counter-team worked examples |
| `headers_pokemon_6_if_none_match_304.txt` | response headers of `GET /pokemon/6` sent with `If-None-Match: W/"677f8-3Krcf7jpPYlpXGuwcBxA8vW6glE"` |
| `census_curl_log.txt` | `curl -w "{id} %{http_code} %{time_total} %{size_download}"` output for one `GET /pokemon/{id}` per listed entry, 4 in parallel (`xargs -P 4`) |
| `census_all_pokemon.tsv` | **Derived, not raw.** One row per entry, extracted from the 1351 bodies of that sweep: id, name, `species.name`, `is_default`, types in slot order, the six `base_stat` values, `sprites.front_default` |

### Facts verified by these captures

10. **Every one of the 1351 detail responses parses the same way** (`census_all_pokemon.tsv`):
    HTTP 200 for all; `id` matches the URL; 586 have one type and 765 have two,
    slots numbered 1..n, no repeated type; every type name is one of the 18
    standard types; `stats` is always the six names in the order of fact 5;
    every `base_stat` is an integer from 1 to 255.
11. **`sprites.front_default` is `null` for 9 entries**: ids 10264–10271 (Koraidon
    and Miraidon build/mode forms) and 10301 (`zygarde-mega`). The other 1342 are
    URLs under `https://raw.githubusercontent.com/PokeAPI/sprites/`.
12. **`is_default` is true exactly for ids below 10000** (1025 entries). Those
    1025 have 1025 distinct `species.name` values, and every alternate form's
    species has a default entry. Names are unique; the longest is 27 characters.
13. **The 18 standard types give a complete, self-consistent chart.** Built from
    the `*_damage_to` lists it has 324 cells: 51 at 2×, 61 at ½×, 8 at 0×, 204 at
    1×. The `*_damage_from` lists of every type agree with it cell for cell. No
    standard type's lists mention a non-standard type. `stellar`, `unknown` and
    `shadow` have empty `damage_relations` and an empty `pokemon` list.
14. **Conditional requests work**: `If-None-Match` with the current ETag returns
    `304` with no body (`headers_pokemon_6_if_none_match_304.txt`). The ETag was
    unchanged between the 11-19 and 11-20 captures.
15. **One full pass is small and fast.** 1351 requests at 4 in parallel took 51
    seconds from a home connection (mean 0.14 s per request, slowest 0.35 s),
    6.05 MB on the wire with gzip, 200 MB decoded (not the 400 MB estimated in
    fact 3). The largest body is 743 KB. No request was refused or throttled
    (`census_curl_log.txt`).

## Added 2026-11-21

| File | Request |
|---|---|
| `pokeapi_source_pokemon_species.csv` | `curl https://raw.githubusercontent.com/PokeAPI/pokeapi/master/data/v2/csv/pokemon_species.csv`, saved unmodified. **This is PokéAPI's source table from its GitHub repository, not an API response.** |
| `species_6_charizard.json`, `species_150_mewtwo_legendary.json`, `species_151_mew_mythical.json` | `GET /pokemon-species/{6,150,151}`, captured with `curl -s --compressed` at about 15:21 Eastern, unmodified |

16. **PokéAPI's source data flags 71 species as legendary and 23 as mythical**, out
    of 1,025, with none flagged as both (`is_legendary`, `is_mythical` columns).
    The species IDs 1 to 1,025 are the IDs of the 1,025 default Pokémon entries.
17. **An alternate form names its species in the Pokémon response**: `species.url`
    of `/pokemon/10034` is `.../pokemon-species/6/`
    (`pokemon_10034_nondefault_form.json`).
18. **The species endpoint carries the flags as booleans named `is_legendary`,
    `is_mythical` and `is_baby`**, the same names as the source table's columns.
    Charizard is neither; Mewtwo is legendary; Mew is mythical. The response
    also has a `varieties` list naming every Pokémon entry of the species with
    an `is_default` flag (Charizard: 6, 10034, 10035, 10196). The species list
    endpoint reports `count: 1025`. The three responses are 27 to 35 KB decoded,
    4 to 6 KB on the wire, and each took under 0.3 seconds.

## Added 2026-11-21 (about 22:29 Eastern)

| File | Request |
|---|---|
| `species_list_full.json` | `GET /pokemon-species?limit=100000`, fetched with `curl -s --compressed`, saved unmodified |
| `census_species_curl_log.txt` | `curl -w "{id} %{http_code} %{time_total} %{size_download}"` output for one `GET /pokemon-species/{id}` per listed species, 4 in parallel (`xargs -P 4`) |
| `species_{3,9,25,34,59,76,130,131,135,149,248}_{name}.json`, `species_1007_koraidon_legendary.json` | 12 bodies of that sweep, saved unmodified: the species of the Pokémon whose own responses are in this folder. `koraidon-limited-build` (entry 10264) belongs to species 1007, which is legendary. `species_6_charizard.json` was re-fetched and is byte-identical. |
| `census_all_species.tsv` | **Derived, not raw.** One row per species, extracted from the 1,025 bodies of that sweep: id, name, `is_legendary`, `is_mythical`, `is_baby`, and each entry of `varieties` as its Pokémon id with `default` or `form` |

19. **Every one of the 1,025 species responses has the shape of the three
    captured earlier** (`census_all_species.tsv`): HTTP 200 for all; `id` matches
    the URL; `is_legendary`, `is_mythical` and `is_baby` are always booleans;
    `varieties` is never empty. 71 species are legendary, 23 mythical, none
    both, and every flag equals the source table's (fact 16).
20. **Every Pokémon entry belongs to exactly one species.** The `varieties`
    lists together name 1,351 Pokémon ids, the same 1,351 as the Pokémon census,
    each once. Each species has exactly one default variety, whose id is the
    species id. The species name and the default flag agree with the Pokémon
    census for all 1,351. 158 Pokémon entries belong to a legendary or mythical
    species: the 94 default entries and 64 other forms.
21. **One pass over the species is small and fast.** 1,025 requests at 4 in
    parallel took 33 seconds (mean 0.12 s per request, slowest 0.18 s), 4.5 MB
    on the wire with gzip, 25 MB decoded; the largest body is 10 KB on the wire.
    No request was refused or throttled (`census_species_curl_log.txt`).

## Added 2026-11-22 (about 18:50 Eastern): moves

| File | Request |
|---|---|
| `move_list_full.json` | `GET /move?limit=100000`, fetched with `curl -s --compressed`, saved unmodified |
| `census_moves_curl_log.txt` | `curl -w "{id} %{http_code} %{time_total} %{size_download}"` output for one `GET /move/{id}` per listed move, 4 in parallel (`xargs -P 4`) |
| `census_all_moves.tsv` | **Derived, not raw.** One row per move, extracted from the 938 bodies of that sweep: id, name, type, damage class, power, accuracy, pp, priority, target, generation, the fields of `meta` (category, hit counts, turn counts, drain, healing), and how many Pokémon its `learned_by_pokemon` list names |
| `move_{id}_{name}.json` (14 files) | 14 bodies of that sweep, saved unmodified, one for each kind the rules mention: ordinary special and physical moves (53, 89, 444, 411), fixed damage (69), one-hit knock-out (90), multi-hit (3), charge (76), recharge (63), the user faints (153), no accuracy (129), a status move (45), the non-standard `shadow` type (10001), and a move whose `meta` is null (827) |

22. **The move list has 938 entries.** 920 have ids from 1 upward; 18 have ids
    from 10001 to 10018 and are all of type `shadow`, which is not one of the 18
    standard types. No Pokémon learns any of those 18.
23. **Every move answer has the same top-level keys**, among them `type`,
    `damage_class`, `power`, `accuracy`, `meta` and `learned_by_pokemon`. The
    damage class is `physical` for 395, `special` for 266 and `status` for 277.
    No status move has a power. **There is no flag for moves that charge,
    recharge or make the user faint**: no `flags` key exists, `meta` has no such
    field, and `meta` is null for 111 moves (the newest ones).
24. **`power` is null for 77 of the 661 damaging moves**: 4 one-hit knock-outs
    and 73 whose damage is fixed or depends on something else (`seismic-toss`,
    `low-kick`, `return`). **`accuracy` is null for 92 damaging moves** (moves
    that do not check accuracy, such as `swift`), and is `0` for one,
    `tachyon-cutter`.
25. **573 damaging moves have a power and a standard type.** 514 of them have a
    power of 120 or less; 59 are stronger, of which 44 are learned by some
    Pokémon (`explosion` 250, `self-destruct` 200, the ten recharge moves at
    150 and 160, `focus-punch` 150, and others in the census file). 27 counted
    moves hit more than once (`min_hits` and `max_hits` set); their `power` is
    for one hit.
26. **A Pokémon's own `moves` array and the moves' `learned_by_pokemon` lists
    agree.** For each of the 14 captured Pokémon answers, the set of moves in
    its `moves` array equals the set of moves that name it, with no difference
    either way. Across all moves, 1,317 of the 1,351 Pokémon are named by at
    least one; the 34 that are not are the Gigantamax forms (ids 10195 to
    10228). 7 default Pokémon learn moves but none that deals damage with a
    stated power: Ditto, Wobbuffet, Smeargle, Wynaut, Pyukumuku, Cosmog and
    Cosmoem. There are 102,342 Pokémon-and-move pairs; the median Pokémon
    learns 77 moves.
27. **One pass over the moves is small and fast.** 938 requests at 4 in parallel
    took 26 seconds (mean 0.10 s per request, slowest 0.58 s), 3.2 MB on the
    wire with gzip, 31 MB decoded. No request was refused or throttled
    (`census_moves_curl_log.txt`).

## Not verified by these captures

- What `x-pokeapi-hash` / `x-pokeapi-deploy-date` actually track. They look like a
  data-deploy fingerprint that could make change detection cheap, but their
  semantics are a guess until confirmed in PokéAPI's docs or source.
- Whether the ETag changes whenever, and only when, the body changes. Fact 14
  shows a 304 is returned; it does not show what the ETag is computed from.
- Which moves need a turn to charge or recharge, or have another drawback. The
  move answer has no field for it (fact 23), and 73 of the 531 learnable moves
  with a power have no English effect text to read it from.
- PokéAPI rate limits. Fact 15 shows one pass at 4 in parallel was not
  throttled; it says nothing about higher rates or repeated passes.
- Whether `raw.githubusercontent.com` throttles a browser that loads many
  sprites.

(Resolved on 2026-11-20: null sprites, fact 11; conditional requests, fact 14.
Resolved on 2026-11-21: the species responses' shape and the time of one pass,
facts 19 to 21.)
