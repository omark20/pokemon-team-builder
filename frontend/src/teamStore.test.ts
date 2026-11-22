// The team rules, run against a stand-in backend that records every request.
import { expect, test, vi } from "vitest";
import { MESSAGES, nextTeamName, TeamStore } from "./teamStore";
import { byName } from "./test/census";
import { FakeServer } from "./test/fakeServer";
import type { Team } from "./types";

const PIKACHU = byName("pikachu"); // id 25
const CHARIZARD = byName("charizard"); // id 6

async function start(teams: Team[] = []) {
  const server = new FakeServer(teams);
  const store = new TeamStore();
  await store.load();
  return { server, store, state: () => store.getState() };
}

const team = (id: number, name: string, pokemon_ids: number[] = []): Team => ({ id, name, pokemon_ids });

test("the first Add creates 'Team 1', then adds the Pokémon to it and selects it", async () => {
  const { server, store, state } = await start();
  expect(await store.add(PIKACHU)).toBe(true);
  expect(server.writes()).toEqual([
    ["POST /api/teams", { name: "Team 1" }],
    ["PUT /api/teams/1/members", { pokemon_ids: [25] }],
  ]);
  expect(state().teams).toEqual([team(1, "Team 1", [25])]);
  expect(state().activeId).toBe(1);
});

test("a second Add while the first team is being created makes no second team", async () => {
  const { server, store, state } = await start();
  const release = server.hold();
  const first = store.add(PIKACHU);
  const second = store.add(CHARIZARD);
  release();
  expect(await Promise.all([first, second])).toEqual([true, false]);
  expect(state().teams).toEqual([team(1, "Team 1", [25])]);
});

test.each([
  { refusal: [429, 1800], text: MESSAGES.tooFastMinutes },
  { refusal: [429, 5], text: MESSAGES.tooFastSeconds },
  { refusal: [500], text: MESSAGES.createFailed },
  { refusal: [409], text: MESSAGES.tooManyTeams },
])("a refused create ($refusal) makes no team and says why", async ({ refusal, text }) => {
  const { server, store, state } = await start();
  server.refuseNext("POST", refusal[0]!, refusal[1]);
  expect(await store.add(PIKACHU)).toBe(false);
  expect(state().teams).toEqual([]);
  expect(state().notice).toEqual({ kind: "error", text });
});

test("if the first Add's second request fails, 'Team 1' stays empty and the next Add fills it", async () => {
  const { server, store, state } = await start();
  server.refuseNext("PUT", 500);
  expect(await store.add(PIKACHU)).toBe(false);
  expect(state().teams).toEqual([team(1, "Team 1")]);
  expect(state().activeId).toBe(1);
  expect(state().notice?.text).toBe(MESSAGES.halfDone("Team 1"));

  expect(await store.add(PIKACHU)).toBe(true);
  await vi.waitFor(() => expect(server.teams).toEqual([team(1, "Team 1", [25])]));
});

test("Add accepts a Pokémon the team already has", async () => {
  const { server, store } = await start([team(1, "Team 1", [6])]);
  expect(await store.add(CHARIZARD)).toBe(true);
  await vi.waitFor(() => expect(server.teams[0]?.pokemon_ids).toEqual([6, 6]));
});

test("Add is refused at six members with a message and no request", async () => {
  const { server, store, state } = await start([team(1, "Team 1", [1, 2, 3, 4, 5, 6])]);
  expect(await store.add(PIKACHU)).toBe(false);
  expect(state().notice).toEqual({ kind: "error", text: MESSAGES.teamFull });
  expect(server.writes()).toEqual([]);
});

test.each([
  { refusal: [500], text: MESSAGES.saveFailed },
  { refusal: [429, 5], text: MESSAGES.tooFastSeconds },
  { refusal: [429, 90], text: MESSAGES.tooFastMinutes },
])("a failed save ($refusal) puts the team back and says so", async ({ refusal, text }) => {
  const { server, store, state } = await start([team(1, "Team 1", [6, 9])]);
  server.refuseNext("PUT", refusal[0]!, refusal[1]);
  store.setMembers(1, [9, 6]);
  expect(state().teams[0]?.pokemon_ids).toEqual([9, 6]); // shown at once
  await vi.waitFor(() => expect(state().notice).toEqual({ kind: "error", text }));
  expect(state().teams[0]?.pokemon_ids).toEqual([6, 9]);
});

test("quick changes are saved one at a time and the last one wins", async () => {
  const { server, store } = await start([team(1, "Team 1", [6, 9, 25])]);
  const release = server.hold();
  store.setMembers(1, [9, 6, 25]);
  store.setMembers(1, [9, 25, 6]);
  store.setMembers(1, [25, 9, 6]);
  expect(server.writes()).toHaveLength(1); // the second and third wait for the first
  release();
  await vi.waitFor(() => expect(server.teams[0]?.pokemon_ids).toEqual([25, 9, 6]));
  // The middle list was overtaken before it was sent.
  expect(server.writes().map(([, body]) => body.pokemon_ids)).toEqual([[9, 6, 25], [25, 9, 6]]);
});

test.each([
  { names: [], expected: "Team 1" },
  { names: ["Team 1", "Rain team", "Team 4"], expected: "Team 5" },
  { names: ["Team 10 backup"], expected: "Team 1" },
])("a new team after $names is named $expected", ({ names, expected }) => {
  expect(nextTeamName(names.map((name, index) => team(index + 1, name)))).toBe(expected);
});

test("'New team' adds an empty team with the next name and selects it", async () => {
  const { store, state } = await start([team(1, "Team 1", [6])]);
  await store.newTeam();
  expect(state().teams).toEqual([team(1, "Team 1", [6]), team(2, "Team 2")]);
  expect(state().activeId).toBe(2);
});

test("renaming changes only that team's name", async () => {
  const { server, store, state } = await start([team(1, "Team 1", [6]), team(2, "Team 2")]);
  await store.rename(1, "Rain team");
  expect(server.writes()).toEqual([["PATCH /api/teams/1", { name: "Rain team" }]]);
  expect(state().teams).toEqual([team(1, "Rain team", [6]), team(2, "Team 2")]);
});

test("deleting the selected team leaves the others and selects its neighbour", async () => {
  const { server, store, state } = await start([team(1, "A"), team(2, "B", [25]), team(3, "C")]);
  store.select(2);
  await store.remove(2);
  expect(server.writes()).toEqual([["DELETE /api/teams/2", {}]]);
  expect(state().teams).toEqual([team(1, "A"), team(3, "C")]);
  expect(state().activeId).toBe(3);
});

test("a failed load is reported, and loading again recovers", async () => {
  const server = new FakeServer([team(1, "Team 1")]);
  const store = new TeamStore();
  server.refuseNext("GET", 500);
  await store.load();
  expect(store.getState().status).toBe("failed");
  await store.load();
  expect(store.getState()).toMatchObject({ status: "ready", activeId: 1 });
});
