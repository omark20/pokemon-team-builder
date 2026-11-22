// What a team's member list becomes after each thing a visitor can do to a
// slot. Everything acts on a position in the list, never on a Pokémon, so a
// team holding the same Pokémon twice behaves like any other.

export const TEAM_SIZE = 6;

// Two slots trade places; nothing else moves.
export function swapSlots(ids: number[], a: number, b: number): number[] {
  const next = [...ids];
  [next[a], next[b]] = [ids[b]!, ids[a]!];
  return next;
}

// A slot dropped on an empty place goes to the end: a team has no gaps.
export function moveToEnd(ids: number[], from: number): number[] {
  return [...removeSlot(ids, from), ids[from]!];
}

export function removeSlot(ids: number[], index: number): number[] {
  return ids.filter((_, position) => position !== index);
}
