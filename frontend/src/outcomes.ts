// How the page writes the end of a fight: a class that tints it green for a win,
// neutral for a draw and red for a loss; a mark and a word for the table; and
// the turns, which are counted up to 10, shown as "10 or more".
import type { Outcome } from "./types";

export const OUTCOME_CLASS: Record<Outcome, string> = {
  wins: "outcome-win",
  "draws with": "outcome-draw",
  "loses to": "outcome-loss",
};

export const OUTCOME_MARK: Record<Outcome, string> = { wins: "✓", "draws with": "–", "loses to": "✗" };

export const OUTCOME_WORD: Record<Outcome, string> = { wins: "wins", "draws with": "draws", "loses to": "loses" };

const MOST_TURNS = 10;

export const turnCount = (turns: number) => (turns === MOST_TURNS ? "10 or more" : String(turns));

export const turnsWord = (turns: number) => (turns === 1 ? "turn" : "turns");
