// A word for a matchup's points, so a reader who does not play can tell a
// good number from a bad one without a key. A matchup is the counter's damage
// on its opponent minus the damage it takes back, one point per doubling.
export function matchupWord(points: number): string {
  if (points >= 2) return "Strong";
  if (points === 1) return "Good";
  if (points === 0) return "Even";
  if (points === -1) return "Weak";
  return "Bad";
}

// "+3" or "-1": a plus sign for gains, as the reason sentences write them.
export const signed = (points: number) => (points > 0 ? `+${points}` : String(points));
