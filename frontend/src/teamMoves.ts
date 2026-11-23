// What a team's slots become after each thing a visitor can do to a slot.
// Everything acts on a position, never on a Pokémon, so a team holding the same
// Pokémon twice behaves like any other; and the moves chosen for a slot travel
// with it, because each edit is applied to both of a team's lists alike.
import type { Members } from "./types";

export const TEAM_SIZE = 6;

// Two slots trade places; nothing else moves.
export function swapSlots<T>(list: T[], a: number, b: number): T[] {
  const next = [...list];
  [next[a], next[b]] = [list[b]!, list[a]!];
  return next;
}

// A slot dropped on an empty place goes to the end: a team has no gaps.
export function moveToEnd<T>(list: T[], from: number): T[] {
  return [...removeSlot(list, from), list[from]!];
}

export function removeSlot<T>(list: T[], index: number): T[] {
  return list.filter((_, position) => position !== index);
}

// One edit applied to the Pokémon and to their chosen moves.
export function editMembers(members: Members, edit: <T>(list: T[]) => T[]): Members {
  return { pokemon_ids: edit(members.pokemon_ids), moves: edit(members.moves) };
}
