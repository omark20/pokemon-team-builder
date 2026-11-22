// Reordering and removing slots by drag, arrows and "×", checked by the list
// each action sends. Charizard (6) is in two slots on purpose.
import { act, fireEvent, render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import { CENSUS } from "../test/census";
import type { Team } from "../types";
import { TeamHalf } from "./TeamHalf";

const BY_ID = new Map(CENSUS.map((entry) => [entry.id, entry]));

function renderHalf(pokemon_ids: number[]) {
  const onMembers = vi.fn();
  const team: Team = { id: 1, name: "Team 1", pokemon_ids };
  const { container } = render(
    <TeamHalf team={team} pokemonById={BY_ID} onMembers={onMembers} onRename={vi.fn()} onDelete={vi.fn()} />,
  );
  const slots = () => [...container.querySelectorAll<HTMLElement>(".slot")];
  return { onMembers, slots };
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
  expect(onMembers).toHaveBeenCalledExactlyOnceWith([25, 9, 3, 6, 94, 149]);
});

test("dropping a slot on an empty outline moves it to the end", () => {
  const { onMembers, slots } = renderHalf([6, 9, 25]);
  drag(slots()[0]!, slots()[4]!);
  expect(onMembers).toHaveBeenCalledExactlyOnceWith([9, 25, 6]);
});

test("the arrows swap a slot with its neighbour; the first has no earlier, the last no later", () => {
  const { onMembers } = renderHalf([6, 9, 25]);
  expect(screen.queryByRole("button", { name: "Move Charizard earlier" })).toBeNull();
  expect(screen.queryByRole("button", { name: "Move Pikachu later" })).toBeNull();
  fireEvent.click(control("Move Blastoise later")); // keyboard activation: detail 0
  fireEvent.click(control("Move Blastoise earlier"));
  expect(onMembers.mock.calls).toEqual([[[6, 25, 9]], [[9, 6, 25]]]);
});

test("'×' on the second of two Charizard slots removes only that slot", () => {
  const { onMembers } = renderHalf([6, 6, 25]);
  fireEvent.click(control("Remove Charizard", 1));
  expect(onMembers).toHaveBeenCalledExactlyOnceWith([6, 25]);
});

test("on an unrevealed slot the first tap only reveals the controls, and the next one acts", () => {
  const { onMembers, slots } = renderHalf([6, 9, 25]);
  tap(control("Remove Blastoise"));
  expect(onMembers).not.toHaveBeenCalled();
  expect(slots()[1]!.classList.contains("revealed")).toBe(true);
  tap(control("Remove Blastoise"));
  expect(onMembers).toHaveBeenCalledExactlyOnceWith([6, 25]);
});

test("a mouse over the slot reveals its controls, so one click acts", () => {
  const { onMembers, slots } = renderHalf([6, 9, 25]);
  fireEvent.pointerEnter(slots()[1]!, { pointerType: "mouse" });
  fireEvent.pointerDown(control("Move Blastoise earlier"), { pointerType: "mouse" });
  fireEvent.click(control("Move Blastoise earlier"), { detail: 1 });
  expect(onMembers).toHaveBeenCalledExactlyOnceWith([9, 6, 25]);
});

test("every slot control can be reached with Tab, and focusing one reveals its slot", () => {
  const { slots } = renderHalf([6, 9]);
  const controls = screen.getAllByRole("button").filter((button) => button.closest(".slot"));
  expect(controls.map((button) => button.getAttribute("aria-label"))).toEqual([
    "Remove Charizard", "Move Charizard later", "Remove Blastoise", "Move Blastoise earlier",
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
