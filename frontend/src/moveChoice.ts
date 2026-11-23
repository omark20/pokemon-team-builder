// The facts and rules behind choosing a team member's moves: what one move is,
// how the list is ordered and narrowed, and the four positions a choice fills.
import { displayName, moveName, type TypeName } from "./types";

// One move a Pokémon may use in a fight.
export interface MoveOption {
  id: number;
  name: string;
  type: TypeName;
  damage_class: "physical" | "special";
  power: number;
  accuracy: number | null; // null or 0: the move cannot miss
}

// What the dialog loads for one Pokémon: the moves it may use and its usual four.
export interface MoveChoices {
  moves: MoveOption[];
  usual: number[];
  moves_listed: boolean; // false when PokéAPI lists no moves for it at all
}

export const MOST_MOVES = 4;

// Each position holds a move ID or nothing; there are always four.
export type Positions = (number | null)[];

export function positionsOf(ids: number[]): Positions {
  return Array.from({ length: MOST_MOVES }, (_, index) => ids[index] ?? null);
}

export const inUse = (positions: Positions) => positions.filter((id): id is number => id !== null);

// A move goes into the first empty position; with none empty nothing changes.
export function withMove(positions: Positions, id: number): Positions {
  const empty = positions.indexOf(null);
  return empty === -1 ? positions : positions.map((held, index) => (index === empty ? id : held));
}

export const withoutMove = (positions: Positions, id: number) => positions.map((held) => (held === id ? null : held));

// Whether two lists hold the same moves, in any order.
export function sameMoves(a: number[], b: number[]): boolean {
  return a.length === b.length && a.every((id) => b.includes(id));
}

// Strongest first, then by name.
export function byStrength(moves: MoveOption[]): MoveOption[] {
  return [...moves].sort((a, b) => b.power - a.power || a.name.localeCompare(b.name));
}

// The moves whose name contains the search text, of the chosen type ("" for all).
export function matching(moves: MoveOption[], search: string, type: string): MoveOption[] {
  const text = search.trim().toLowerCase();
  return moves.filter((move) => (!type || move.type === type) && moveName(move.name).toLowerCase().includes(text));
}

export const accuracyText = (move: MoveOption) => (move.accuracy ? `${move.accuracy}%` : "never misses");

// "Special · power 130 · 90% accurate", or "… · never misses".
export function classLine(move: MoveOption): string {
  const accuracy = move.accuracy ? `${move.accuracy}% accurate` : "never misses";
  return `${displayName(move.damage_class)} · power ${move.power} · ${accuracy}`;
}
