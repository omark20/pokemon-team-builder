// The team rules, run against a stand-in backend that records every request.
import { expect, test, vi } from "vitest";
import { MESSAGES } from "./messages";
import { nextTeamName, TeamStore } from "./teamStore";
import { byName } from "./test/census";
import { FakeServer } from "./test/fakeServer";
import type { Team } from "./types";
import { makeTeam, usualMembers } from "./test/makeTeam";

const PIKACHU = byName("pikachu"); // id 25
const CHARIZARD = byName("charizard"); // id 6

async function start(teams: Team[] = []) {
  const server = new FakeServer(teams);
  const store = new TeamStore();
  await store.load();
  return { server, store, state: () => store.getState() };
}

// Waits until every request already answered, and every step waiting on it, has
// run: a timer of 0 fires only after all pending promise steps are done.
const allSettled = () => new Promise((resolve) => setTimeout(resolve, 0));

test("the first Add creates 'Team 1', then adds the Pokémon to it and selects it", async () => {
  const { server, store, state } = await start();
  expect(await store.add(PIKACHU)).toBe(true);
  expect(server.writes()).toEqual([
    ["POST /api/teams", { name: "Team 1" }],
    ["PUT /api/teams/1/members", { pokemon_ids: [25], move_ids: [null] }],
  ]);
  expect(state().teams).toEqual([makeTeam(1, "Team 1", [25])]);
  expect(state().activeId).toBe(1);
});

test("a second Add while the first team is being created makes no second team", async () => {
  const { server, store, state } = await start();
  const release = server.hold();
  const first = store.add(PIKACHU);
  const second = store.add(CHARIZARD);
  release();
  expect(await Promise.all([first, second])).toEqual([true, false]);
  expect(state().teams).toEqual([makeTeam(1, "Team 1", [25])]);
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
  expect(state().teams).toEqual([makeTeam(1, "Team 1")]);
  expect(state().activeId).toBe(1);
  expect(state().notice?.text).toBe(MESSAGES.halfDone("Team 1"));

  expect(await store.add(PIKACHU)).toBe(true);
  await vi.waitFor(() => expect(server.teams).toEqual([makeTeam(1, "Team 1", [25])]));
});

test("Add accepts a Pokémon the team already has", async () => {
  const { server, store } = await start([makeTeam(1, "Team 1", [6])]);
  expect(await store.add(CHARIZARD)).toBe(true);
  await vi.waitFor(() => expect(server.teams[0]?.pokemon_ids).toEqual([6, 6]));
});

test("Add is refused at six members with a message and no request", async () => {
  const { server, store, state } = await start([makeTeam(1, "Team 1", [1, 2, 3, 4, 5, 6])]);
  expect(await store.add(PIKACHU)).toBe(false);
  expect(state().notice).toEqual({ kind: "error", text: MESSAGES.teamFull });
  expect(server.writes()).toEqual([]);
});

test.each([
  { refusal: [500], text: MESSAGES.saveFailed },
  { refusal: [429, 5], text: MESSAGES.tooFastSeconds },
  { refusal: [429, 90], text: MESSAGES.tooFastMinutes },
])("a failed save ($refusal) puts the team back and says so", async ({ refusal, text }) => {
  const { server, store, state } = await start([makeTeam(1, "Team 1", [6, 9])]);
  server.refuseNext("PUT", refusal[0]!, refusal[1]);
  store.setMembers(1, usualMembers([9, 6]));
  expect(state().teams[0]?.pokemon_ids).toEqual([9, 6]); // shown at once
  await vi.waitFor(() => expect(state().notice).toEqual({ kind: "error", text }));
  expect(state().teams[0]?.pokemon_ids).toEqual([6, 9]);
});

test("quick changes are saved one at a time and the last one wins", async () => {
  const { server, store } = await start([makeTeam(1, "Team 1", [6, 9, 25])]);
  const release = server.hold();
  store.setMembers(1, usualMembers([9, 6, 25]));
  store.setMembers(1, usualMembers([9, 25, 6]));
  store.setMembers(1, usualMembers([25, 9, 6]));
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
  expect(nextTeamName(names.map((name, index) => makeTeam(index + 1, name)))).toBe(expected);
});

test("'New team' adds an empty team with the next name and selects it", async () => {
  const { store, state } = await start([makeTeam(1, "Team 1", [6])]);
  await store.newTeam();
  expect(state().teams).toEqual([makeTeam(1, "Team 1", [6]), makeTeam(2, "Team 2")]);
  expect(state().activeId).toBe(2);
});

test("renaming changes only that team's name", async () => {
  const { server, store, state } = await start([makeTeam(1, "Team 1", [6]), makeTeam(2, "Team 2")]);
  await store.rename(1, "Rain team");
  expect(server.writes()).toEqual([["PATCH /api/teams/1", { name: "Rain team" }]]);
  expect(state().teams).toEqual([makeTeam(1, "Rain team", [6]), makeTeam(2, "Team 2")]);
});

test("deleting the selected team leaves the others and selects its neighbour", async () => {
  const { server, store, state } = await start([makeTeam(1, "A"), makeTeam(2, "B", [25]), makeTeam(3, "C")]);
  store.select(2);
  await store.remove(2);
  expect(server.writes()).toEqual([["DELETE /api/teams/2", {}]]);
  expect(state().teams).toEqual([makeTeam(1, "A"), makeTeam(3, "C")]);
  expect(state().activeId).toBe(3);
});

test("a failed load is reported, and loading again recovers", async () => {
  const server = new FakeServer([makeTeam(1, "Team 1")]);
  const store = new TeamStore();
  server.refuseNext("GET", 500);
  await store.load();
  expect(store.getState().status).toBe("failed");
  await store.load();
  expect(store.getState()).toMatchObject({ status: "ready", activeId: 1 });
});

test("a build waits for the team's pending save, so the server works from the latest members", async () => {
  const { server, store, state } = await start([makeTeam(1, "Team 1", [6])]);
  const release = server.hold();
  store.setMembers(1, usualMembers([6, 9]));
  const building = store.buildCounter();
  await allSettled();
  expect(server.calls.at(-1)?.path).toBe("/api/teams/1/members"); // no counter request yet
  release();
  await building;
  expect(server.calls.at(-1)?.path).toBe("/api/teams/1/counter");
  expect(state().counter).not.toBeNull();
});

test("an answer for members that changed while it was worked out is dropped", async () => {
  const { server, store, state } = await start([makeTeam(1, "Team 1", [6, 9])]);
  const release = server.hold();
  const building = store.buildCounter();
  await vi.waitFor(() => expect(server.calls.at(-1)?.path).toBe("/api/teams/1/counter"));
  store.setMembers(1, usualMembers([9, 6]));
  release();
  await building;
  expect(state().counter).toBeNull();
});

test.each([
  { refusal: 503, detail: "The legendary flags are not loaded yet", text: "The legendary flags are not loaded yet" },
  { refusal: 503, detail: "Counter teams are busy", text: "Counter teams are busy" },
  { refusal: 500, detail: undefined, text: MESSAGES.counterFailed },
  { refusal: 429, detail: undefined, text: MESSAGES.tooFastSeconds },
])("a refused build ($refusal) shows no team and says why: $text", async ({ refusal, detail, text }) => {
  const { server, store, state } = await start([makeTeam(1, "Team 1", [6])]);
  server.refuseNext("GET", refusal, 30, "/api/teams/1/counter", detail);
  await store.buildCounter();
  expect(state()).toMatchObject({ counter: null, building: false, counterError: text });
});

test("the legendary tick is sent with the next build, and the answer shown is the one for it", async () => {
  const { server, store, state } = await start([makeTeam(1, "Team 1", [6])]);
  store.setLeaveOutLegendary(true);
  expect(server.calls.at(-1)?.path).toBe("/api/teams"); // ticking asks nothing
  await store.buildCounter();
  expect(state().counter?.legendary_left_out).toBe(true);
  store.setLeaveOutLegendary(false);
  await store.buildCounter();
  expect(state().counter?.legendary_left_out).toBe(false);
});

// A counter answer must answer what is on screen. Each case starts a build of
// team 1's counter, changes something while it is in flight, then lets it finish.
const counterRequests = (server: FakeServer) => server.calls.filter((call) => call.path.includes("/counter"));

test("an answer for a team that was left while its save was in flight is dropped", async () => {
  const { server, store, state } = await start([makeTeam(1, "A", [6]), makeTeam(2, "B", [25])]);
  const release = server.hold(); // holds the save of team 1's new member
  await store.add(CHARIZARD);
  const building = store.buildCounter();
  store.select(2);
  release();
  await building;
  expect(state()).toMatchObject({ activeId: 2, counter: null, counterError: null, building: false });
  expect(counterRequests(server)).toEqual([]);
});

test("an answer for the legendary setting the box no longer shows is dropped", async () => {
  const { server, store, state } = await start([makeTeam(1, "A", [6])]);
  const release = server.hold(); // holds the counter request
  const building = store.buildCounter();
  await vi.waitFor(() => expect(counterRequests(server)).toHaveLength(1));
  store.setLeaveOutLegendary(true);
  release();
  await building;
  expect(state()).toMatchObject({ counter: null, leaveOutLegendary: true });
});

test("an error for a team deleted mid-build is not shown on the tab that replaces it", async () => {
  const { server, store, state } = await start([makeTeam(1, "A", [6]), makeTeam(2, "B", [25])]);
  server.refuseNext("GET", 500, undefined, "/api/teams/1/counter");
  const release = server.hold(); // holds the counter request
  const building = store.buildCounter();
  await vi.waitFor(() => expect(counterRequests(server)).toHaveLength(1));
  await store.remove(1);
  release();
  await building;
  expect(state()).toMatchObject({ activeId: 2, counterError: null });
});

test("switching tab mid-build leaves Build usable on the new tab", async () => {
  const { server, store, state } = await start([makeTeam(1, "A", [6]), makeTeam(2, "B", [25])]);
  server.hold();
  void store.buildCounter();
  store.select(2);
  expect(state().building).toBe(false);
});

test.each([
  { when: "the teams are still loading", arrange: async () => new TeamStore(), text: MESSAGES.teamsLoading },
  {
    when: "the teams failed to load",
    arrange: async () => {
      new FakeServer().refuseNext("GET", 500);
      const store = new TeamStore();
      await store.load();
      return store;
    },
    text: MESSAGES.teamsFailed,
  },
])("an Add while $when says why nothing happened", async ({ arrange, text }) => {
  const store = await arrange();
  expect(await store.add(PIKACHU)).toBe(false);
  expect(store.getState().notice).toEqual({ kind: "error", text });
});

test("an Add while the first team is still being created says to wait", async () => {
  const { server, store, state } = await start();
  const release = server.hold();
  const first = store.add(PIKACHU);
  expect(await store.add(CHARIZARD)).toBe(false);
  expect(state().notice).toEqual({ kind: "error", text: MESSAGES.stillCreating });
  release();
  await first;
});

test("'Save as new team' that stops half way says so in its own words", async () => {
  const { server, store, state } = await start([makeTeam(1, "Team 1", [6, 9, 3])]);
  await store.buildCounter();
  server.refuseNext("PUT", 500);
  await store.saveCounterAsTeam();
  expect(state().notice).toEqual({ kind: "error", text: MESSAGES.counterNotSaved("Team 2") });
});

test("a save that fails for a team deleted meanwhile reports nothing", async () => {
  const { server, store, state } = await start([makeTeam(1, "A", [6]), makeTeam(2, "B")]);
  const release = server.hold(); // holds the save; the team is then deleted
  store.setMembers(1, usualMembers([6, 9]));
  await store.remove(1);
  release();
  await allSettled(); // the save is answered 404, and the store has handled it
  expect(state().notice).toBeNull();
});

const FOCUS_BLAST = [{ id: 411, name: "focus-blast" }];

test("choosing a slot's moves saves them with the team, clears the counter team and reports success", async () => {
  const { server, store, state } = await start([makeTeam(1, "Team 1", [6, 9])]);
  await store.buildCounter();
  expect(state().counter).not.toBeNull();
  expect(await store.setMoves(1, 1, FOCUS_BLAST)).toBe(true);
  expect(server.writes()).toEqual([["PUT /api/teams/1/members", { pokemon_ids: [6, 9], move_ids: [null, [411]] }]]);
  expect(state().teams[0]?.moves).toEqual([null, FOCUS_BLAST]);
  expect(state().counter).toBeNull();
});

test("if saving moves fails, the slot goes back, the error shows and the call says so", async () => {
  const { server, store, state } = await start([makeTeam(1, "Team 1", [6, 9])]);
  server.refuseNext("PUT", 500);
  expect(await store.setMoves(1, 0, FOCUS_BLAST)).toBe(false);
  expect(state().teams[0]?.moves).toEqual([null, null]);
  expect(state().notice).toEqual({ kind: "error", text: MESSAGES.saveFailed });
});
