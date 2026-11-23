// What "Show details" opens under the face-off: one card per pick showing the
// turns each side needs to knock the other out, then, behind "Show more", every
// fight in one table, the moves your team is assumed to carry, and how the team
// was chosen.
import { useState } from "react";
import { displayName, moveName, type AssumedMoves, type ChosenMove, type CounterResult, type SlotMoves } from "../types";
import { FightTable } from "./FightTable";
import { PickCard } from "./PickCard";

export const INTRO =
  "Each counter was picked to win a one-on-one fight against one of your Pokémon. The numbers are the turns each needs to knock out the other; fewer wins.";

const SIZE_WORDS = ["", "one", "two", "three", "four", "five", "six"];

// The last sentence names the team's size: "The six shown are the best six that are all different."
function howChosen(size: number): string[] {
  const words = SIZE_WORDS[size];
  const shown =
    size === 1 ? "The one shown is the best one." : `The ${words} shown are the best ${words} that are all different.`;
  return [
    "Each counter fights each of your Pokémon at level 50, each using the best of its four moves.",
    "A counter is judged first on its own opponent, then on how much better it does against your team than against Pokémon in general, then on its base stats.",
    shown,
  ];
}

// The names of moves as a reader sees them: "Focus Blast and Swift".
const namesOf = (moves: { name: string }[]) => moves.map((move) => moveName(move.name)).join(" and ");

// Under a member's line: the chosen moves it could not use.
function DroppedMoves({ moves, name }: { moves: ChosenMove[]; name: string }) {
  if (moves.length === 0) return null;
  const are = moves.length === 1 ? "is" : "are";
  return (
    <span className="moves-gone">
      {namesOf(moves)} {are} no longer listed for {name}, so not used.
    </span>
  );
}

// One member's moves as used, marked as chosen by the visitor or as its usual
// four. A chosen move missing from the moves used is one a later scan no longer
// lists; if none of the chosen moves is left, the usual four were used.
function MovesLine({ member, chosen }: { member: AssumedMoves; chosen: SlotMoves }) {
  const name = displayName(member.name);
  const moves = member.moves.map(moveName).join(", ");
  const gone = chosen?.filter((move) => !member.moves.includes(move.name)) ?? [];
  const ownInUse = (chosen?.length ?? 0) > gone.length;
  return (
    <li>
      <strong>{name}</strong>:{" "}
      {member.moves_listed ? moves || "No damaging move" : "PokéAPI lists no moves for this Pokémon"}
      {member.moves_listed && <span className="moves-source"> · {ownInUse ? "chosen by you" : "usual"}</span>}
      <DroppedMoves moves={gone} name={name} />
    </li>
  );
}

// What "Show more" reveals: three sections, each under a small heading.
interface DetailsProps {
  counter: CounterResult;
  chosen: SlotMoves[]; // the moves chosen for each of the visitor's slots
}

function MoreDetails({ counter, chosen }: DetailsProps) {
  const fights = counter.picks.length * counter.opponent_moves.length;
  return (
    <div id="counter-more" className="counter-more">
      <section aria-labelledby="fights-title">
        <h3 id="fights-title">All {fights} fights</h3>
        <p className="section-note">A tick means the counter wins that one-on-one fight. Outlined: the opponent it was picked for.</p>
        <FightTable counter={counter} />
      </section>
      <section aria-labelledby="moves-title">
        <h3 id="moves-title">Your team's moves</h3>
        <p className="section-note">
          The four each of your Pokémon is assumed to carry: the four that together hit the most Pokémon hardest.
        </p>
        <ul className="team-moves">
          {counter.opponent_moves.map((member, index) => (
            <MovesLine key={index} member={member} chosen={chosen[index] ?? null} />
          ))}
        </ul>
      </section>
      <section aria-labelledby="chosen-title">
        <h3 id="chosen-title">How this team was chosen</h3>
        <p className="section-note">{howChosen(counter.picks.length).join(" ")}</p>
      </section>
    </div>
  );
}

export function CounterDetails({ counter, chosen }: DetailsProps) {
  const [more, setMore] = useState(false);
  return (
    <div className="counter-details">
      <p>{INTRO}</p>
      <div className="pick-cards">
        {counter.picks.map((pick, slot) => (
          <PickCard key={slot} pick={pick} slot={slot} />
        ))}
      </div>
      <button type="button" className="more-toggle" aria-expanded={more} aria-controls="counter-more" onClick={() => setMore(!more)}>
        {more ? "Show less" : "Show more"}
      </button>
      {more && <MoreDetails counter={counter} chosen={chosen} />}
    </div>
  );
}
