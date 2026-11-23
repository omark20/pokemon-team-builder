// Reordering and removing slots by drag, arrows and "×", checked by the members
// each action sends, and choosing a slot's moves. Charizard (6) is in two slots
// on purpose.
import { act, fireEvent, render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import { CENSUS } from "../test/census";
import type { MoveChoices } from "../moveChoice";
import charizardMoves from "../test/charizardMoves.json";
import type { SlotMoves, Team } from "../types";
import { TeamHalf } from "./TeamHalf";
import { makeTeam, usualMembers } from "../test/makeTeam";

const BY_ID = new Map(CENSUS.map((entry) => [entry.id, entry]));

function renderHalf(pokemon_ids: number[], moves?: SlotMoves[], saved = true) {
  const onMembers = vi.fn();
  const onMoves = vi.fn().mockResolvedValue(saved);
  const loadMoves = vi.fn().mockResolvedValue(charizardMoves as MoveChoices);
  const team: Team = { ...makeTeam(1, "Team 1", pokemon_ids), ...(moves && { moves }) };
  const { container } = render(
    <TeamHalf
      team={team}
      pokemonById={BY_ID}
      onMembers={onMembers}
      onMoves={onMoves}
      loadMoves={loadMoves}
      onRename={vi.fn()}
      onDelete={vi.fn()}
    />,
  );
  const slots = () => [...container.querySelectorAll<HTMLElement>(".slot")];
  return { onMembers, onMoves, slots };
}

const control = (label: string, nth = 0) => screen.getAllByRole("button", { name: label })[nth]!;
// A tap on a touch screen: a press, then a click (detail 1 marks a pointer click).
const tap = (element: HTMLElement) => {
  fireEvent.pointerDown(element, { pointerType: "touch" });
  fireEvent.click(element, { detail: 1 });
};

function drag(from: HTMLElement, to: HTMLElement) {
  const dataTransfer = { setData: vi.fn(), effectAllowed: "" };
  fireEvent.dragStart(from, { dataTransfer });
  fireEvent.dragOver(to, { dataTransfer });
  fireEvent.drop(to, { dataTransfer });
}

test("dropping slot 1 on slot 4 swaps the two and moves nothing else", () => {
  const { onMembers, slots } = renderHalf([6, 9, 3, 25, 94, 149]);
  drag(slots()[0]!, slots()[3]!);
  expect(onMembers).toHaveBeenCalledExactlyOnceWith(usualMembers([25, 9, 3, 6, 94, 149]));
});

test("a drag cancelled before its drop leaves nothing to drop later", () => {
  const { onMembers, slots } = renderHalf([6, 9, 3, 25]);
  const dataTransfer = { setData: vi.fn(), effectAllowed: "" };
  fireEvent.dragStart(slots()[0]!, { dataTransfer });
  fireEvent.dragEnd(slots()[0]!, { dataTransfer }); // Esc, or let go outside the team
  fireEvent.drop(slots()[3]!, { dataTransfer }); // then something else is dropped here
  expect(onMembers).not.toHaveBeenCalled();
});

test("dropping a slot on an empty outline moves it to the end", () => {
  const { onMembers, slots } = renderHalf([6, 9, 25]);
  drag(slots()[0]!, slots()[4]!);
  expect(onMembers).toHaveBeenCalledExactlyOnceWith(usualMembers([9, 25, 6]));
});

test("the arrows swap a slot with its neighbour; the first has no earlier, the last no later", () => {
  const { onMembers } = renderHalf([6, 9, 25]);
  expect(screen.queryByRole("button", { name: "Move Charizard earlier" })).toBeNull();
  expect(screen.queryByRole("button", { name: "Move Pikachu later" })).toBeNull();
  fireEvent.click(control("Move Blastoise later")); // keyboard activation: detail 0
  fireEvent.click(control("Move Blastoise earlier"));
  expect(onMembers.mock.calls).toEqual([[usualMembers([6, 25, 9])], [usualMembers([9, 6, 25])]]);
});

test("'×' on the second of two Charizard slots removes only that slot", () => {
  const { onMembers } = renderHalf([6, 6, 25]);
  fireEvent.click(control("Remove Charizard", 1));
  expect(onMembers).toHaveBeenCalledExactlyOnceWith(usualMembers([6, 25]));
});

test("on an unrevealed slot the first tap only reveals the controls, and the next one acts", () => {
  const { onMembers, slots } = renderHalf([6, 9, 25]);
  tap(control("Remove Blastoise"));
  expect(onMembers).not.toHaveBeenCalled();
  expect(slots()[1]!.classList.contains("revealed")).toBe(true);
  tap(control("Remove Blastoise"));
  expect(onMembers).toHaveBeenCalledExactlyOnceWith(usualMembers([6, 25]));
});

test("a mouse over the slot reveals its controls, so one click acts", () => {
  const { onMembers, slots } = renderHalf([6, 9, 25]);
  fireEvent.pointerEnter(slots()[1]!, { pointerType: "mouse" });
  fireEvent.pointerDown(control("Move Blastoise earlier"), { pointerType: "mouse" });
  fireEvent.click(control("Move Blastoise earlier"), { detail: 1 });
  expect(onMembers).toHaveBeenCalledExactlyOnceWith(usualMembers([9, 6, 25]));
});

test("every slot control can be reached with Tab, and focusing one reveals its slot", () => {
  const { slots } = renderHalf([6, 9]);
  const controls = screen.getAllByRole("button").filter((button) => button.closest(".slot"));
  expect(controls.map((button) => button.getAttribute("aria-label"))).toEqual([
    "Remove Charizard", "Move Charizard later", "Choose Charizard's moves",
    "Remove Blastoise", "Move Blastoise earlier", "Choose Blastoise's moves",
  ]);
  expect(controls.every((button) => button.tabIndex === 0)).toBe(true);
  act(() => controls[0]!.focus());
  expect(slots()[0]!.classList.contains("revealed")).toBe(true);
});

test("six positions are drawn, the unfilled ones as outlines", () => {
  const { slots } = renderHalf([6, 9]);
  expect(slots().map((slot) => slot.classList.contains("slot-empty"))).toEqual([
    false, false, true, true, true, true,
  ]);
  expect(screen.getByText("2 of 6")).toBeTruthy();
});

const FOCUS_BLAST = [{ id: 411, name: "focus-blast" }];

test("a slot's chosen moves travel with it when it moves, go with it when it is removed, and show as 'own moves'", () => {
  const { onMembers, slots } = renderHalf([6, 9, 25], [null, FOCUS_BLAST, null]);
  expect(slots().map((slot) => slot.querySelector(".slot-own")?.textContent ?? null)).toEqual([
    null, "own moves", null, null, null, null,
  ]);
  fireEvent.click(control("Move Blastoise earlier"));
  fireEvent.click(control("Remove Blastoise"));
  expect(onMembers.mock.calls).toEqual([
    [{ pokemon_ids: [9, 6, 25], moves: [FOCUS_BLAST, null, null] }],
    [{ pokemon_ids: [6, 25], moves: [null, null] }],
  ]);
});

test("by keyboard, 'Moves' opens the slot's picker, and closing it returns focus there", async () => {
  const { slots } = renderHalf([6, 9]);
  const moves = control("Choose Charizard's moves");
  act(() => moves.focus());
  expect(slots()[0]!.classList.contains("revealed")).toBe(true);
  fireEvent.click(moves, { detail: 0 }); // Enter or Space on a focused button
  expect(await screen.findByRole("dialog", { name: "Charizard's moves" })).toBeTruthy();
  fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });
  expect(screen.queryByRole("dialog")).toBeNull();
  expect(document.activeElement).toBe(control("Choose Charizard's moves"));
});

test("on a phone the first tap on 'Moves' reveals the controls and the next opens the picker", async () => {
  renderHalf([6, 9]);
  tap(control("Choose Charizard's moves"));
  expect(screen.queryByRole("dialog")).toBeNull();
  tap(control("Choose Charizard's moves"));
  expect(await screen.findByRole("dialog", { name: "Charizard's moves" })).toBeTruthy();
});

test.each([
  { saved: true, open: false },
  { saved: false, open: true },
])("saving sends the slot's moves; the picker closes only once they are saved (saved: $saved)", async ({ saved, open }) => {
  const { onMoves } = renderHalf([6, 9], undefined, saved);
  fireEvent.click(control("Choose Charizard's moves"), { detail: 0 });
  await screen.findByRole("searchbox");
  fireEvent.click(screen.getByRole("button", { name: "Remove Earthquake" }));
  await act(async () => fireEvent.click(screen.getByRole("button", { name: "Save" })));
  expect(onMoves).toHaveBeenCalledExactlyOnceWith(0, [
    { id: 315, name: "overheat" },
    { id: 542, name: "hurricane" },
    { id: 200, name: "outrage" },
  ]);
  expect(screen.queryByRole("dialog") !== null).toBe(open);
});
