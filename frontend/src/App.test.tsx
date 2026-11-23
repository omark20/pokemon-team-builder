// The whole page against a stand-in backend: loading states, and the paths
// that cross from the grid to the face-off card.
import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import App from "./App";
import { MESSAGES } from "./messages";
import { FakeServer } from "./test/fakeServer";
import { makeTeam } from "./test/makeTeam";

const count = () => screen.findByText(/^Showing /);
const teamHalf = (name: string) => within(screen.getByRole("region", { name }));

test("shows placeholder cards, then the grid loaded from the app's own API", async () => {
  const server = new FakeServer();
  render(<App />);
  expect(screen.getByLabelText("Loading Pokémon")).toBeTruthy();
  expect((await count()).textContent).toBe("Showing 60 of 1,351");
  // The five reads the page makes on opening, and nothing else.
  expect(server.calls.map((call) => call.path).sort()).toEqual([
    "/api/alerts", "/api/pokemon", "/api/scan/status", "/api/session", "/api/teams",
  ]);
});

test("a failed list request shows the list-failed state, and 'Try again' loads the list", async () => {
  const server = new FakeServer();
  server.refuseNext("GET", 500, undefined, "/api/pokemon");
  render(<App />);
  expect(await screen.findByText("Couldn't load Pokémon")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Try again" }));
  expect((await count()).textContent).toBe("Showing 60 of 1,351");
});

test("a first-time visitor's Add creates 'Team 1' holding that Pokémon", async () => {
  new FakeServer();
  render(<App />);
  expect(await screen.findByText("Build your first team")).toBeTruthy();
  await count();
  fireEvent.click(screen.getAllByRole("button", { name: "Add to team" })[0]!); // Bulbasaur
  expect(await screen.findByRole("button", { name: "Team 1", pressed: true })).toBeTruthy();
  expect(teamHalf("Team 1").getByText("Bulbasaur")).toBeTruthy();
});

test("Enter on a full team adds nothing, shows the team-full message and keeps the query", async () => {
  const server = new FakeServer([makeTeam(1, "Team 1", [1, 2, 3, 4, 5, 6])]);
  render(<App />);
  await count();
  const search = screen.getByRole("searchbox");
  fireEvent.change(search, { target: { value: "pikachu" } });
  fireEvent.keyDown(search, { key: "Enter" });
  expect(await screen.findByText(MESSAGES.teamFull, { selector: ".notice-bar span" })).toBeTruthy();
  expect((search as HTMLInputElement).value).toBe("pikachu");
  expect(server.writes()).toEqual([]);
});

test("a team named with HTML shows the text itself", async () => {
  const name = "<img src=x onerror=alert(1)>";
  new FakeServer([makeTeam(1, name)]);
  const { container } = render(<App />);
  expect(await screen.findByRole("heading", { name })).toBeTruthy();
  expect(container.querySelector("img[src='x']")).toBeNull();
});

test("switching tabs shows the other team", async () => {
  new FakeServer([makeTeam(1, "Fire", [6]), makeTeam(2, "Water", [9])]);
  render(<App />);
  await count();
  expect(teamHalf("Fire").getByText("Charizard")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Water" }));
  expect(teamHalf("Water").getByText("Blastoise")).toBeTruthy();
  expect(screen.queryByRole("region", { name: "Fire" })).toBeNull();
});

test("Delete asks first, and removes the team only when confirmed", async () => {
  const server = new FakeServer([makeTeam(1, "Fire"), makeTeam(2, "Water")]);
  const confirm = vi.spyOn(window, "confirm").mockReturnValueOnce(false).mockReturnValueOnce(true);
  render(<App />);
  const remove = await screen.findByRole("button", { name: "Delete" });
  fireEvent.click(remove);
  expect(server.writes()).toEqual([]);
  fireEvent.click(remove);
  expect(await screen.findByRole("button", { name: "Water", pressed: true })).toBeTruthy();
  expect(confirm).toHaveBeenCalledTimes(2);
  expect(server.writes()).toEqual([["DELETE /api/teams/1", {}]]);
});

test("Rename saves the trimmed name", async () => {
  const server = new FakeServer([makeTeam(1, "Team 1")]);
  render(<App />);
  fireEvent.click(await screen.findByRole("button", { name: "Rename" }));
  const box = screen.getByRole("textbox", { name: "Team name" }) as HTMLInputElement;
  // The old name is selected, so typing replaces it rather than adding to it.
  expect([box.selectionStart, box.selectionEnd]).toEqual([0, "Team 1".length]);
  fireEvent.change(box, { target: { value: "  Rain team " } });
  fireEvent.click(screen.getByRole("button", { name: "Save" }));
  expect(await screen.findByRole("heading", { name: "Rain team" })).toBeTruthy();
  expect(server.writes()).toEqual([["PATCH /api/teams/1", { name: "Rain team" }]]);
});

test("after a keyboard move, focus follows the moved Pokémon to its new place", async () => {
  new FakeServer([makeTeam(1, "Team 1", [6, 9, 25])]);
  render(<App />);
  await count();
  fireEvent.click(teamHalf("Team 1").getByRole("button", { name: "Move Charizard later" }));
  fireEvent.click(document.activeElement!); // Enter again on whatever has focus
  expect(teamHalf("Team 1").getAllByText(/^(Charizard|Blastoise|Pikachu)$/).map((el) => el.textContent)).toEqual([
    "Blastoise", "Pikachu", "Charizard",
  ]);
  expect(document.activeElement?.getAttribute("aria-label")).toBe("Move Charizard earlier");
});

test("switching tab closes an open rename form, so the typed name renames nothing", async () => {
  const server = new FakeServer([makeTeam(1, "Team 1"), makeTeam(2, "Team 2")]);
  render(<App />);
  fireEvent.click(await screen.findByRole("button", { name: "Rename" }));
  fireEvent.change(screen.getByRole("textbox", { name: "Team name" }), { target: { value: "Typed for 1" } });
  fireEvent.click(screen.getByRole("button", { name: "Team 2" }));
  expect(screen.queryByRole("textbox", { name: "Team name" })).toBeNull();
  expect(screen.getByRole("heading", { name: "Team 2" })).toBeTruthy();
  expect(server.writes()).toEqual([]);
});

test("a notice is announced from a region already on the page, and a repeat is announced again", async () => {
  new FakeServer([makeTeam(1, "Team 1")]);
  render(<App />);
  await count();
  const polite = document.querySelector('.notice-live[aria-live="polite"]')!;
  expect(polite.textContent).toBe("");
  const add = screen.getAllByRole("button", { name: "Add to team" })[0]!;
  await act(async () => fireEvent.click(add));
  const first = polite.firstElementChild;
  expect(first?.textContent).toBe("Bulbasaur added to Team 1.");
  await act(async () => fireEvent.click(add));
  expect(polite.firstElementChild).not.toBe(first); // a new node, so it is read again
  expect(document.querySelector('.notice-live[aria-live="polite"]')).toBe(polite);
});

test("after a Delete, focus is on the tab now selected", async () => {
  new FakeServer([makeTeam(1, "Fire"), makeTeam(2, "Water")]);
  vi.spyOn(window, "confirm").mockReturnValue(true);
  render(<App />);
  await act(async () => fireEvent.click(await screen.findByRole("button", { name: "Delete" })));
  expect(document.activeElement).toBe(screen.getByRole("button", { name: "Water", pressed: true }));
});

test.each(["Save", "Cancel"])("after %s in the rename form, focus is back on Rename", async (closing) => {
  new FakeServer([makeTeam(1, "Team 1")]);
  render(<App />);
  fireEvent.click(await screen.findByRole("button", { name: "Rename" }));
  await act(async () => fireEvent.click(screen.getByRole("button", { name: closing })));
  expect(document.activeElement).toBe(screen.getByRole("button", { name: "Rename" }));
});
