-- Every table and index the app uses, applied at every start-up, so every statement is
-- safe to run again. A column added to a table that already exists is an ALTER here.

-- One row per scan run: the visible record that the scheduled job runs.
CREATE TABLE IF NOT EXISTS scan_runs (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    started_at timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz,
    status text NOT NULL CHECK (status IN ('running', 'ok', 'incomplete', 'failed')),
    scope text NOT NULL CHECK (scope IN ('full', 'subset')),
    scanned integer NOT NULL DEFAULT 0,
    changed integer NOT NULL DEFAULT 0,
    failed integer NOT NULL DEFAULT 0,
    note text  -- internal only, never returned by the API
);

-- At most one run in progress. A second trigger fails on this index, which is the 409.
CREATE UNIQUE INDEX IF NOT EXISTS scan_runs_one_running
    ON scan_runs (status) WHERE status = 'running';

-- The stored copy of PokéAPI. One column per field of PokemonRecord (domain/diff.py),
-- same names; a new field is a new column added nullable with no default, with an
-- ALTER TABLE ... ADD COLUMN IF NOT EXISTS line here. Rows are never deleted.
-- The limit of the first-sight rule: a new column that PokéAPI itself may send as null
-- (one listed in OPTIONAL_UPSTREAM) would have its first fill recorded as changes.
CREATE TABLE IF NOT EXISTS pokemon (
    id integer PRIMARY KEY,
    name text NOT NULL,
    is_default boolean NOT NULL,
    types text[] NOT NULL CHECK (cardinality(types) BETWEEN 1 AND 2),
    hp smallint NOT NULL CHECK (hp >= 0),
    attack smallint NOT NULL CHECK (attack >= 0),
    defense smallint NOT NULL CHECK (defense >= 0),
    special_attack smallint NOT NULL CHECK (special_attack >= 0),
    special_defense smallint NOT NULL CHECK (special_defense >= 0),
    speed smallint NOT NULL CHECK (speed >= 0),
    sprite_url text,
    removed_at timestamptz,  -- set when PokéAPI stops serving the entry
    updated_at timestamptz NOT NULL DEFAULT now()
);
-- From each Pokémon's species response. Added after the table first existed, so empty in
-- old rows until the next scan fills them (with no change recorded).
ALTER TABLE pokemon ADD COLUMN IF NOT EXISTS is_legendary boolean;
ALTER TABLE pokemon ADD COLUMN IF NOT EXISTS is_mythical boolean;

-- The 18 x 18 type chart: how much each attacking type multiplies damage to each defender.
CREATE TABLE IF NOT EXISTS type_effectiveness (
    attacker text NOT NULL,
    defender text NOT NULL,
    multiplier real NOT NULL CHECK (multiplier IN (0, 0.5, 1, 2)),
    PRIMARY KEY (attacker, defender)
);

-- One row per changed field of a Pokémon, or per changed chart cell. Values are JSON,
-- so a sprite going to or from none is the JSON value null, not SQL NULL.
CREATE TABLE IF NOT EXISTS changes (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    pokemon_id integer REFERENCES pokemon (id),
    attacker text,
    defender text,
    field text NOT NULL,  -- a pokemon column, 'status', or 'multiplier'
    old_value jsonb NOT NULL,
    new_value jsonb NOT NULL,
    detected_at timestamptz NOT NULL,
    scan_run_id bigint NOT NULL REFERENCES scan_runs (id),
    is_demo boolean NOT NULL DEFAULT false,
    CHECK ((pokemon_id IS NULL) <> (attacker IS NULL)),
    CHECK ((attacker IS NULL) = (defender IS NULL))
);
CREATE INDEX IF NOT EXISTS changes_detected_at ON changes (detected_at);

-- Visitors. The cookie holds a random value; only its SHA-256 is stored, so
-- nothing here can be turned back into a working cookie. Nothing else about a person.
CREATE TABLE IF NOT EXISTS users (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,  -- never sent to any client
    token_hash bytea NOT NULL UNIQUE,
    created_at timestamptz NOT NULL DEFAULT now()
);

-- Optional accounts, added to a table that already existed: a record is either anonymous (a token, no username)
-- or an account (a username and a password hash, no token); the code keeps it so.
-- username_key is the name in lower case, so Ash and ash are one name.
ALTER TABLE users ALTER COLUMN token_hash DROP NOT NULL;
ALTER TABLE users ADD COLUMN IF NOT EXISTS username text;
ALTER TABLE users ADD COLUMN IF NOT EXISTS username_key text;
ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash text;
CREATE UNIQUE INDEX IF NOT EXISTS users_username_key ON users (username_key);

-- One row per browser signed in to an account; its cookie's SHA-256, as for anonymous
-- visitors. A session lasts 30 days from sign-in.
CREATE TABLE IF NOT EXISTS sessions (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id bigint NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    token_hash bytea NOT NULL UNIQUE,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS sessions_user_id ON sessions (user_id);

CREATE TABLE IF NOT EXISTS teams (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id bigint NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    name text NOT NULL CHECK (char_length(name) BETWEEN 1 AND 50),
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS teams_user_id ON teams (user_id);

-- One row per slot, numbered 1 to n with no gaps. A slot, not a Pokémon, is the row's
-- identity, so the same Pokémon may fill several slots; there is deliberately no
-- uniqueness on (team_id, pokemon_id). The key and the position check make a seventh
-- slot impossible.
CREATE TABLE IF NOT EXISTS team_members (
    team_id bigint NOT NULL REFERENCES teams (id) ON DELETE CASCADE,
    position smallint NOT NULL CHECK (position BETWEEN 1 AND 6),
    pokemon_id integer NOT NULL REFERENCES pokemon (id),
    PRIMARY KEY (team_id, position)
);
CREATE INDEX IF NOT EXISTS team_members_pokemon_id ON team_members (pokemon_id);

-- An alert a visitor has dismissed stays dismissed for that visitor only.
CREATE TABLE IF NOT EXISTS dismissals (
    user_id bigint NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    change_id bigint NOT NULL REFERENCES changes (id) ON DELETE CASCADE,
    PRIMARY KEY (user_id, change_id)
);

-- The demo's "pretend PokéAPI said this" document. At most one row.
CREATE TABLE IF NOT EXISTS demo_overrides (
    only_row boolean PRIMARY KEY DEFAULT true CHECK (only_row),
    doc jsonb NOT NULL
);
