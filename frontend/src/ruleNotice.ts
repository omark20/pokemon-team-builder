// The one notice the counter half can show: when the team breaks the rule that no
// opposing type may hit more than half the counters for 2× or more, it names the
// type (or types) hitting the most counters, how many, and why no better-mixed
// team is shown.
import { displayName, type CounterResult } from "./types";

// "Water and Rock": the types one counter is weak to (an opponent has at most two).
const listed = (names: string[]) => names.join(" and ");

// "A", "A, and B" or "A, B, and C".
function joined(parts: string[]): string {
  return parts.length > 1 ? `${parts.slice(0, -1).join(", ")}, and ${parts.at(-1)}` : parts[0]!;
}

export function ruleNotice(counter: CounterResult): string | null {
  if (counter.weakness_rule === "kept") return null;
  const most = Math.max(...Object.values(counter.weakness_counts));
  const types = Object.entries(counter.weakness_counts)
    .filter(([, count]) => count === most)
    .map(([type]) => displayName(type));
  const size = counter.picks.length;
  // A team of one never reaches the search's limit (that search takes one step per
  // candidate), so a single counter breaks the rule only when every candidate does.
  if (size === 1) {
    const { counter: pick, opponent } = counter.picks[0]!;
    const theirs = displayName(opponent.name);
    return `${displayName(pick.name)} is weak to ${listed(types)}. Every Pokémon that could be picked to counter ${theirs} is weak to one of its types.`;
  }
  // Each type keeps its own count ("Fire, and 4 to Rock"): "Fire and Rock" would say the same counters are weak to both.
  const [first, ...others] = types;
  const weak = [`${most} of these ${size} counters are weak to ${first}`, ...others.map((type) => `${most} to ${type}`)];
  const why =
    counter.weakness_rule === "limit_raised"
      ? `No possible counter team has fewer than ${most} weak to one of your team's types.`
      : "This is the strongest team before the mix of types is considered; the search for a better-mixed one was stopped at its limit.";
  return `${joined(weak)}. ${why}`;
}
