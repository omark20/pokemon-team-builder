// The change-alert panel and the tab dots, through the whole page against a
// stand-in backend. Alpha holds Charizard (6) and Venusaur (3); Beta holds
// Pikachu (25).
import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { expect, test } from "vitest";
import App from "../App";
import { ALERT_MESSAGES } from "../alerts";
import { FakeServer } from "../test/fakeServer";
import type { Alert } from "../types";

const TEAMS = [
  { id: 1, name: "Alpha", pokemon_ids: [6, 3] },
  { id: 2, name: "Beta", pokemon_ids: [25] },
];

const change = (id: number, pokemonId: number, oldValue: number, newValue: number): Alert => ({
  id, pokemon_id: pokemonId, attacker: null, defender: null, field: "attack", old_value: oldValue,
  new_value: newValue, detected_at: "2026-11-20T12:00:00Z", is_demo: false, your_pokemon: [pokemonId],
});

async function start(alerts: Alert[]) {
  const server = new FakeServer(TEAMS);
  server.alerts = alerts;
  render(<App />);
  await screen.findByText(/^Showing /);
  return server;
}

const panel = () => within(screen.getByRole("region", { name: "Changes to your Pokémon" }));
const rows = () => [...document.querySelectorAll(".alert-row")];
const dotted = () => [...document.querySelectorAll(".tab")].filter((tab) => tab.querySelector(".tab-dot")).map((tab) => tab.textContent);
const dismissPaths = (server: FakeServer) => server.writes().map(([call]) => call);

test("a headline count and one row per change, old value struck through and new value bold", async () => {
  await start([change(11, 6, 84, 94), change(12, 25, 55, 60)]);
  expect(panel().getByText("2 changes to your Pokémon this week")).toBeTruthy();
  expect(rows()).toHaveLength(2);
  const first = rows()[0]!;
  expect(first.querySelector("s")?.textContent).toBe("84");
  expect(first.querySelector("b")?.textContent).toBe("94");
  expect(first.textContent).toContain("Charizard");
  expect(first.textContent).toContain("teams: Alpha");
});

test("no alerts, no panel", async () => {
  await start([]);
  expect(screen.queryByRole("region", { name: "Changes to your Pokémon" })).toBeNull();
});

test("a tab has a dot exactly when its team holds an alerted Pokémon, and loses it on Dismiss", async () => {
  const server = await start([change(11, 6, 84, 94)]);
  expect(dotted()).toEqual(["Alpha"]);
  expect(screen.getByRole("img", { name: "has a change alert" }).closest("button")?.textContent).toBe("Alpha");
  await act(async () => fireEvent.click(panel().getByRole("button", { name: "Dismiss" })));
  expect(dismissPaths(server)).toEqual(["POST /api/alerts/11/dismiss"]);
  expect(dotted()).toEqual([]);
  expect(screen.queryByRole("region", { name: "Changes to your Pokémon" })).toBeNull();
});

test("'Dismiss all' dismisses each alert in turn", async () => {
  const server = await start([change(11, 6, 84, 94), change(12, 25, 55, 60), change(13, 3, 82, 80)]);
  await act(async () => fireEvent.click(panel().getByRole("button", { name: "Dismiss all" })));
  expect(dismissPaths(server)).toEqual([
    "POST /api/alerts/11/dismiss", "POST /api/alerts/12/dismiss", "POST /api/alerts/13/dismiss",
  ]);
  expect(rows()).toHaveLength(0);
});

test("'Dismiss all' stops at a refusal, says so, and keeps the rest", async () => {
  const server = await start([change(11, 6, 84, 94), change(12, 25, 55, 60), change(13, 3, 82, 80)]);
  server.refuseNext("POST", 429, 30, "/api/alerts/12/dismiss");
  await act(async () => fireEvent.click(panel().getByRole("button", { name: "Dismiss all" })));
  expect(dismissPaths(server)).toEqual(["POST /api/alerts/11/dismiss", "POST /api/alerts/12/dismiss"]);
  expect(rows()).toHaveLength(2);
  expect(panel().getByRole("alert").textContent).toBe(ALERT_MESSAGES.dismissAllStopped);
});

test("an alert for a Pokémon taken off every team leaves the panel", async () => {
  await start([change(12, 25, 55, 60)]);
  fireEvent.click(screen.getByRole("button", { name: /^Beta/ }));
  fireEvent.click(screen.getByRole("button", { name: "Remove Pikachu" }));
  expect(screen.queryByRole("region", { name: "Changes to your Pokémon" })).toBeNull();
});

test("nothing on the page announces demo mode while the demo is active", async () => {
  const server = new FakeServer(TEAMS);
  server.demoActive = true;
  render(<App />);
  await screen.findByText(/^Showing /);
  expect(document.body.textContent?.toLowerCase()).not.toContain("demo");
});
