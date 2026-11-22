// A word for a matchup's points, so a reader who does not play can tell a
// good number from a bad one without a key, and the colour that goes with
// the word. A matchup is the counter's damage on its opponent minus the
// damage it takes back, one point per doubling. Word and colour both come
// from `matchupLevel`, so they can never disagree.
import type { CSSProperties } from "react";
import { MATCHUP_COLOURS, type MatchupLevel } from "./colours";

const WORDS: Record<MatchupLevel, string> = {
  strong: "Strong",
  good: "Good",
  even: "Even",
  weak: "Weak",
  bad: "Bad",
};

// +2 or more strong, +1 good, 0 even, -1 weak, -2 or less bad.
export function matchupLevel(points: number): MatchupLevel {
  if (points >= 2) return "strong";
  if (points === 1) return "good";
  if (points === 0) return "even";
  if (points === -1) return "weak";
  return "bad";
}

export const matchupWord = (points: number) => WORDS[matchupLevel(points)];

// The custom properties --matchup-fill and --matchup-text for these points.
export function matchupStyle(points: number): CSSProperties {
  const colour = MATCHUP_COLOURS[matchupLevel(points)];
  return { "--matchup-fill": colour.fill, "--matchup-text": colour.text } as CSSProperties;
}

// "+3" or "-1": a plus sign for gains, as the reason sentences write them.
export const signed = (points: number) => (points > 0 ? `+${points}` : String(points));
