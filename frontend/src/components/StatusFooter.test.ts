import { expect, test } from "vitest";
import type { ScanRun } from "../types";
import { describeRun } from "./StatusFooter";

const run = (change: Partial<ScanRun>): ScanRun => ({
  started_at: "2026-11-22T01:53:27Z", finished_at: "2026-11-22T01:53:41Z", status: "ok", scanned: 1351, changed: 0, ...change,
});

test.each([
  { state: "no run yet", input: undefined, expected: /^PokéAPI has not been checked/ },
  { state: "a run in progress", input: run({ status: "running", finished_at: null }), expected: /^Checking PokéAPI for changes now/ },
  { state: "a finished run", input: run({ changed: 2 }), expected: /: 1,351 Pokémon scanned, 2 changes found\.$/ },
  { state: "one change", input: run({ changed: 1 }), expected: /1 change found\.$/ },
  { state: "a failed run", input: run({ status: "failed" }), expected: /; that check failed\.$/ },
])("the footer describes $state", ({ input, expected }) => {
  expect(describeRun(input)).toMatch(expected);
});
