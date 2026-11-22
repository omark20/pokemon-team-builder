import { expect, test } from "vitest";
import { moveToEnd, removeSlot, swapSlots } from "./teamMoves";

// 6 appears twice on purpose: a team may hold the same Pokémon in two slots.
const TEAM = [6, 9, 6, 25, 94, 149];

test.each([
  { move: "slot 1 dropped on slot 4 swaps the two", result: swapSlots(TEAM, 0, 3), expected: [25, 9, 6, 6, 94, 149] },
  { move: "slot 6 dropped on slot 1 swaps the two", result: swapSlots(TEAM, 5, 0), expected: [149, 9, 6, 25, 94, 6] },
  { move: "a slot swaps with its neighbour", result: swapSlots(TEAM, 1, 2), expected: [6, 6, 9, 25, 94, 149] },
  { move: "slot 2 moves to the end", result: moveToEnd([6, 9, 25], 1), expected: [6, 25, 9] },
  { move: "removing the second of two equal slots keeps the first", result: removeSlot(TEAM, 2), expected: [6, 9, 25, 94, 149] },
])("$move", ({ result, expected }) => {
  expect(result).toEqual(expected);
});

test("a move returns a new list and leaves the old one alone", () => {
  const before = [...TEAM];
  swapSlots(TEAM, 0, 3);
  expect(TEAM).toEqual(before);
});
