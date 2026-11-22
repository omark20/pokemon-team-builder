// The counter half, its details and the footer row, through the whole page
// against a stand-in backend. The team is Charizard, Blastoise, Venusaur and
// the counter answer is test/counterFixture.ts.
import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { expect, test } from "vitest";
import App from "../App";
import { MATCHUP_COLOURS } from "../colours";
import { COUNTER } from "../test/counterFixture";
import { FakeServer } from "../test/fakeServer";
import { NOTICES } from "./CounterHalf";

const TEAM = { id: 1, name: "Team 1", pokemon_ids: [6, 9, 3] };

async function start(teams = [TEAM, { id: 2, name: "Team 2", pokemon_ids: [25] }]) {
  const server = new FakeServer(teams);
  render(<App />);
  await screen.findByText(/^Showing /);
  return server;
}

const counterHalf = () => within(screen.getByRole("region", { name: "Counter team" }));
const footer = () => within(document.querySelector<HTMLElement>(".face-off-footer")!);
const primary = () => footer().getByRole("button", { name: /Build counter team|Rebuild/ }) as HTMLButtonElement;
const counterNames = () => [...document.querySelectorAll(".half[aria-label='Counter team'] .slot-name")].map((el) => el.textContent);

async function build() {
  fireEvent.click(primary());
  await screen.findByText("beats Charizard");
}

test("before a build the right half is an empty box with no button in it", async () => {
  await start();
  expect(counterHalf().getByText("No counter team yet")).toBeTruthy();
  expect(counterHalf().queryByRole("button")).toBeNull();
  expect(primary().textContent).toBe("Build counter team");
  expect(footer().getByText("Drag a Pokémon to reorder, or select it for its arrows and ×.")).toBeTruthy();
});

test("after a build, counter i faces member i, and the footer reports the pool size", async () => {
  const server = await start();
  await build();
  expect(server.calls.at(-1)?.path).toBe("/api/teams/1/counter");
  expect(counterNames()).toEqual(["Archeops", "Hydrapple", "Celesteela"]);
  const beats = [...document.querySelectorAll(".beats")].map((el) => el.textContent);
  expect(beats).toEqual(["beats Charizard", "beats Blastoise", "beats Venusaur"]);
  expect(counterHalf().queryByRole("button", { name: "Why?" })).toBeNull(); // the reasons are in the details
  expect(footer().getByText("Best team out of 1,025 candidates.")).toBeTruthy();
  expect(primary().textContent).toBe("Rebuild");
});

test("an empty team cannot be built, and says what to do", async () => {
  await start([{ id: 1, name: "Team 1", pokemon_ids: [] }]);
  expect(primary().disabled).toBe(true);
  expect(footer().getByText("Add Pokémon from the grid below.")).toBeTruthy();
});

const CHANGES: [string, () => void][] = [
  ["adding a member", () => fireEvent.click(screen.getAllByRole("button", { name: "Add to team" })[0]!)],
  ["removing a member", () => fireEvent.click(screen.getByRole("button", { name: "Remove Blastoise" }))],
  ["reordering", () => fireEvent.click(screen.getByRole("button", { name: "Move Blastoise later" }))],
  ["switching tab", () => fireEvent.click(screen.getByRole("button", { name: "Team 2" }))],
];

test.each(CHANGES)("%s clears the counter team", async (_change, act) => {
  await start();
  await build();
  act();
  expect(await counterHalf().findByText("No counter team yet")).toBeTruthy();
  expect(primary().textContent).toBe("Build counter team");
});

test("the details open on request: each pick with its label but no reason, and a table whose rows add up", async () => {
  await start();
  await build();
  expect(document.querySelector(".counter-details")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Show details" }));
  expect([...document.querySelectorAll(".pick-list li")].map((line) => line.textContent)).toEqual([
    "Archeops beats Charizard Strong +3 Why?",
    "Hydrapple beats Blastoise Strong +3 Why?",
    "Celesteela beats Venusaur Strong +3 Why?",
  ]);
  const details = document.querySelector(".counter-details")!.textContent;
  expect(COUNTER.picks.filter((pick) => details.includes(pick.reason))).toEqual([]); // a reason shows only when its Why? is pressed
  const rows = [...screen.getByRole("table").querySelectorAll("tbody tr")];
  expect(rows.map((row) => row.querySelectorAll("td:not(.row-sum)").length)).toEqual([3, 3, 3]);
  const sums = rows.map((row) => Number(row.querySelector(".row-sum")!.textContent));
  expect(sums).toEqual([3, 1, 2]); // the fixture grid's rows: 3 - 1 + 1, -1 + 3 - 1, -1 + 0 + 3
  // Each cell gives a word and the number; the fixture's first row is +3, -1, +1.
  expect([...rows[0]!.querySelectorAll("td:not(.row-sum)")].map((cell) => cell.textContent)).toEqual([
    "Strong +3", "Weak -1", "Good +1",
  ]);
  expect(screen.getByRole("heading", { name: "How this team was chosen" })).toBeTruthy();
  // The colour follows the word: the "Strong" cell has the strong fill, the "Weak" one the weak fill.
  const fills = [...rows[0]!.querySelectorAll<HTMLElement>("td:not(.row-sum)")].map((cell) =>
    cell.style.getPropertyValue("--matchup-fill"),
  );
  expect(fills).toEqual([MATCHUP_COLOURS.strong.fill, MATCHUP_COLOURS.weak.fill, MATCHUP_COLOURS.good.fill]);
});

test.each([
  { flag: "stopped_early", notice: NOTICES.stoppedEarly, status: "Best team found out of 1,025 candidates." },
  { flag: "relaxed", notice: NOTICES.relaxed, status: "Best team out of 1,025 candidates." },
])("a $flag result shows its notice without opening the details", async ({ flag, notice, status }) => {
  const server = new FakeServer([TEAM]);
  server.counter = { ...COUNTER, [flag]: true };
  render(<App />);
  await screen.findByText(/^Showing /);
  await build();
  expect(counterHalf().getByText(notice)).toBeTruthy();
  expect(footer().getByText(status)).toBeTruthy();
  expect(document.querySelector(".counter-details")).toBeNull();
});

test("the legendary box has its label, starts unticked, and ticking it clears a shown team", async () => {
  const server = await start();
  const box = footer().getByRole("checkbox", { name: "Leave out legendary and mythical Pokémon" }) as HTMLInputElement;
  expect(box.checked).toBe(false);
  await build();
  const requests = server.calls.length;
  fireEvent.click(box);
  expect(counterHalf().getByText("No counter team yet")).toBeTruthy();
  expect(primary().textContent).toBe("Build counter team");
  expect(server.calls).toHaveLength(requests);
});

test.each([
  { leftOut: true, pool: 931, status: "Best team out of 931 candidates, legendary and mythical left out." },
  { leftOut: false, pool: 1025, status: "Best team out of 1,025 candidates." },
])("the status line names the pool the response reports (left out: $leftOut)", async ({ leftOut, pool, status }) => {
  const server = new FakeServer([TEAM]);
  server.counter = { ...COUNTER, pool_size: pool };
  render(<App />);
  await screen.findByText(/^Showing /);
  if (leftOut) fireEvent.click(footer().getByRole("checkbox", { name: "Leave out legendary and mythical Pokémon" }));
  await build();
  expect(footer().getByText(status)).toBeTruthy();
});

test("a refused build shows the server's reason in the counter half", async () => {
  const server = await start();
  server.refuseNext("GET", 503, undefined, "/api/teams/1/counter", "The legendary flags are not loaded yet");
  fireEvent.click(primary());
  expect(await counterHalf().findByText("The legendary flags are not loaded yet", { selector: ".counter-empty" })).toBeTruthy();
});

test("'Save as new team' makes a team of the three counters", async () => {
  const server = await start();
  await build();
  await act(async () => fireEvent.click(footer().getByRole("button", { name: "Save as new team" })));
  expect(server.writes()).toEqual([
    ["POST /api/teams", { name: "Team 3" }],
    ["PUT /api/teams/3/members", { pokemon_ids: [567, 1019, 797] }],
  ]);
  expect(screen.getByRole("button", { name: "Team 3", pressed: true })).toBeTruthy();
});

test("a finished build is announced once, politely, with the counters' names", async () => {
  await start();
  const live = document.querySelector('.counter-live[aria-live="polite"]')!;
  expect(live.textContent).toBe("");
  await build();
  expect(live.textContent).toBe("Counter team ready: Archeops, Hydrapple, Celesteela.");
});

const pickList = () => within(document.querySelector<HTMLElement>(".pick-list")!);
const whyButtons = () => pickList().getAllByRole("button", { name: /^(Why\?|Hide why)$/ });
const shownReasons = () => [...document.querySelectorAll(".why")].map((el) => el.textContent);

async function openDetails() {
  await build();
  fireEvent.click(screen.getByRole("button", { name: "Show details" }));
}

test("a pick line's Why? shows that pick's reason under it, and only that one, until pressed again", async () => {
  await start();
  await openDetails();
  const second = whyButtons()[1]!;
  expect([second.tagName, second.getAttribute("type")]).toEqual(["BUTTON", "button"]); // reachable with Tab, works with Enter
  fireEvent.click(second);
  expect(shownReasons()).toEqual([COUNTER.picks[1]!.reason]);
  expect([second.textContent, second.getAttribute("aria-expanded")]).toEqual(["Hide why", "true"]);
  fireEvent.click(second);
  expect(shownReasons()).toEqual([]);
  expect([second.textContent, second.getAttribute("aria-expanded")]).toEqual(["Why?", "false"]);
});

test("a rebuild hides every open reason", async () => {
  await start();
  await openDetails();
  whyButtons().forEach((button) => fireEvent.click(button));
  expect(shownReasons()).toHaveLength(3);
  fireEvent.click(primary());
  await screen.findByText("beats Charizard");
  fireEvent.click(screen.getByRole("button", { name: "Show details" }));
  expect(shownReasons()).toEqual([]);
});
