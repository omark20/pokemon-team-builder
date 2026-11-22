-- Applied at every start-up, so every statement is safe to run again.
-- Each milestone adds its tables here.

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
