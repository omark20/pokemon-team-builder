// The counter half, its details and the footer row, through the whole page
// against a stand-in backend. The team is Charizard, Blastoise, Venusaur and the
// counter answer is test/counterFixture.ts: Gyarados beats Charizard, Pikachu
// loses to Blastoise, Dragonite draws with Venusaur.
import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { expect, test } from "vitest";
import App from "../App";
import { ruleNotice } from "../ruleNotice";
import { COUNTER } from "../test/counterFixture";
import { FakeServer } from "../test/fakeServer";
import { INTRO } from "./CounterDetails";

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
  expect(counterNames()).toEqual(["Gyarados", "Pikachu", "Dragonite"]);
  const chips = [...document.querySelectorAll(".beats")].map((el) => el.textContent);
  expect(chips).toEqual(["beats Charizard", "loses to Blastoise", "draws with Venusaur"]);
  expect(counterHalf().queryByRole("button", { name: "Why?" })).toBeNull(); // the reasons are in the details
  expect(footer().getByText("Best team out of 3 candidates.")).toBeTruthy();
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

const fighter = (half: Element) =>
  ["fighter-name", "fighter-turns", "fighter-move"].map((part) => half.querySelector(`.${part}`)!.textContent);

test("the details show one scoreboard per pick, the winner's half tinted, and no reason yet", async () => {
  await start();
  await build();
  expect(document.querySelector(".counter-details")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Show details" }));
  expect(screen.getByText(INTRO)).toBeTruthy();
  const cards = [...document.querySelectorAll(".pick-card")].map((card) =>
    [...card.querySelectorAll(".fighter")].map((half) => [...fighter(half), half.classList.contains("outcome-win")]),
  );
  expect(cards).toEqual([
    [["Gyarados", "1 turn", "Aqua Tail", true], ["Charizard", "3 turns", "Outrage", false]], // a win
    [["Pikachu", "2 turns", "Volt Tackle", false], ["Blastoise", "1 turn", "Earthquake", true]], // a loss
    [["Dragonite", "2 turns", "Outrage", false], ["Venusaur", "2 turns", "Outrage", false]], // a draw
  ]);
  const details = document.querySelector(".counter-details")!.textContent;
  expect(COUNTER.picks.filter((pick) => details.includes(pick.reason))).toEqual([]);
  expect(screen.queryByRole("table")).toBeNull(); // behind "Show more"
});

test.each(["kept", "limit_raised", "guard_reached"] as const)("the type-mix notice shows exactly when the rule is not kept (%s)", async (rule) => {
  const server = new FakeServer([TEAM]);
  server.counter = { ...COUNTER, weakness_rule: rule };
  const notice = ruleNotice(server.counter); // its wording is tested in ruleNotice.test.ts
  render(<App />);
  await screen.findByText(/^Showing /);
  await build();
  const shown = [...document.querySelectorAll(".counter-notice")].map((el) => el.textContent);
  expect(shown).toEqual(notice ? [notice] : []);
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
    ["PUT /api/teams/3/members", { pokemon_ids: [130, 25, 149] }],
  ]);
  expect(screen.getByRole("button", { name: "Team 3", pressed: true })).toBeTruthy();
});

test("a finished build is announced once, politely, with the counters' names", async () => {
  await start();
  const live = document.querySelector('.counter-live[aria-live="polite"]')!;
  expect(live.textContent).toBe("");
  await build();
  expect(live.textContent).toBe("Counter team ready: Gyarados, Pikachu, Dragonite.");
});

const whyButtons = () => within(document.querySelector<HTMLElement>(".pick-cards")!).getAllByRole("button", { name: /^(Why\?|Hide why)$/ });
const shownReasons = () => [...document.querySelectorAll(".pick-why")].map((el) => el.textContent);
const moreButton = () => screen.getByRole("button", { name: /^Show (more|less)$/ });

async function openDetails() {
  await build();
  fireEvent.click(screen.getByRole("button", { name: "Show details" }));
}

test("a card's Why? shows that pick's reason, and only that one, until pressed again", async () => {
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

const MORE_HEADINGS = ["All 9 fights", "Your team's moves", "How this team was chosen"];

test("Show more reveals the three sections together, and Show less hides them", async () => {
  await start();
  await openDetails();
  const details = within(document.querySelector<HTMLElement>(".counter-details")!);
  const headings = () => details.queryAllByRole("heading").map((heading) => heading.textContent);
  expect(headings()).toEqual([]);
  fireEvent.click(moreButton());
  expect(headings()).toEqual(MORE_HEADINGS);
  expect(moreButton().getAttribute("aria-expanded")).toBe("true");
  expect(screen.getByText(/The three shown are the best three that are all different\.$/)).toBeTruthy();
  fireEvent.click(moreButton());
  expect(headings()).toEqual([]);
});

test("the table marks every fight, outlines each counter's own opponent and counts its wins", async () => {
  await start();
  await openDetails();
  fireEvent.click(moreButton());
  const rows = [...screen.getByRole("table").querySelectorAll("tbody tr")];
  const marks = rows.map((row) => [...row.querySelectorAll(".fight")].map((cell) => cell.textContent));
  expect(marks).toEqual([["✓", "✓", "✓"], ["✗", "✗", "✗"], ["✓", "✓", "–"]]);
  const outlined = rows.map((row) => [...row.querySelectorAll(".fight")].findIndex((cell) => cell.classList.contains("own")));
  expect(outlined).toEqual([0, 1, 2]);
  expect(rows.map((row) => row.querySelector(".fight-total")!.textContent)).toEqual(["wins 3 of 3", "wins 0 of 3", "wins 2 of 3"]);
});

test("a mark's words are its name, and show under the table when it is pressed or focused", async () => {
  await start();
  await openDetails();
  fireEvent.click(moreButton());
  const mark = screen.getByRole("button", { name: "Pikachu loses: 4 turns against 1" });
  expect(mark.getAttribute("title")).toBe("Pikachu loses: 4 turns against 1");
  fireEvent.focus(mark);
  expect(document.querySelector(".fight-words")!.textContent).toBe("Pikachu loses: 4 turns against 1");
  fireEvent.click(screen.getByRole("button", { name: "Gyarados wins: 1 turn against 3" }));
  expect(document.querySelector(".fight-words")!.textContent).toBe("Gyarados wins: 1 turn against 3");
});

test("your team's moves list each member's four, and say so where PokéAPI lists none", async () => {
  const server = new FakeServer([TEAM]);
  const unlisted = { name: "Venusaur-gmax", moves: [], moves_listed: false };
  server.counter = { ...COUNTER, opponent_moves: [...COUNTER.opponent_moves.slice(0, 2), unlisted] };
  render(<App />);
  await screen.findByText(/^Showing /);
  await openDetails();
  fireEvent.click(moreButton());
  expect([...document.querySelectorAll(".team-moves li")].map((line) => line.textContent)).toEqual([
    "Charizard: Overheat, Earthquake, Hurricane, Outrage",
    "Blastoise: Water Spout, Ice Beam, Outrage, Earthquake",
    "Venusaur-gmax: PokéAPI lists no moves for this Pokémon",
  ]);
});
