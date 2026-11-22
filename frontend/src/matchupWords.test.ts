import { expect, test } from "vitest";
import { matchupWord } from "./matchupWords";

test.each([
  { points: -3, word: "Bad" },
  { points: -2, word: "Bad" },
  { points: -1, word: "Weak" },
  { points: 0, word: "Even" },
  { points: 1, word: "Good" },
  { points: 2, word: "Strong" },
  { points: 3, word: "Strong" },
])("a matchup of $points reads $word", ({ points, word }) => {
  expect(matchupWord(points)).toBe(word);
});
