// The right half of the face-off card: the counter team, three per row, each
// counter in the same position as the team member it answers, with a short
// line saying how their fight ends. Before a team is built it is an empty
// dashed box. When the team breaks the shared-weakness rule, one notice says so
// here, where it is seen without opening the details. After "Show another
// team", a line above the team says which team it is, or why there is no other.
import { typeStyle } from "../colours";
import { OUTCOME_CLASS } from "../outcomes";
import { ruleNotice } from "../ruleNotice";
import { MOST_TEAMS } from "../teamsState";
import { displayName, type CounterPick, type CounterResult, type Pokemon } from "../types";
import { Sprite } from "./Sprite";

interface CounterProps {
  counter: CounterResult | null;
  error: string | null; // why the last build gave no team; shown in the empty box
  pokemonById: Map<number, Pokemon>;
  teamNumber: number; // which team is showing; 1 is the best
  leftOut: number; // how many Pokémon were left out to find it
  onBestTeam: () => void;
}

// Which team is showing after the best, or why there is no other; null for the best.
function otherTeamText(counter: CounterResult, teamNumber: number, leftOut: number): string | null {
  if (counter.no_candidate_for) {
    return `No other team: nothing left hits ${displayName(counter.no_candidate_for)} for 2× or more.`;
  }
  if (teamNumber === 1) return null;
  const which = `Team ${teamNumber}: the best without the ${leftOut} Pokémon shown before.`;
  return teamNumber === MOST_TEAMS ? `${which} That is the tenth team. No more are offered.` : which;
}

// "beats Charizard", "draws with Venusaur" or "loses to Blastoise".
function resultChip(pick: CounterPick): string {
  const verb = pick.outcome === "wins" ? "beats" : pick.outcome;
  return `${verb} ${displayName(pick.opponent.name)}`;
}

// The counters, three per row, each with how its fight ends.
function CounterSlots({ picks, pokemonById }: { picks: CounterPick[]; pokemonById: Map<number, Pokemon> }) {
  return (
    <ol className="slots">
      {picks.map((pick, index) => {
        const known = pokemonById.get(pick.counter.id);
        const name = displayName(pick.counter.name);
        return (
          <li key={index} className="slot" style={known && typeStyle(known.types[0]!)}>
            <Sprite url={known?.sprite_url ?? null} name={name} size={48} />
            <span className="slot-name">{name}</span>
            <span className={`beats ${OUTCOME_CLASS[pick.outcome]}`}>{resultChip(pick)}</span>
          </li>
        );
      })}
    </ol>
  );
}

// What the hidden live line announces once a build ends.
function announcement(counter: CounterResult | null, other: string | null, error: string | null): string | null {
  if (!counter) return error;
  if (counter.no_candidate_for) return other;
  return `Counter team ready: ${counter.picks.map((pick) => displayName(pick.counter.name)).join(", ")}.`;
}

export function CounterHalf({ counter, error, pokemonById, teamNumber, leftOut, onBestTeam }: CounterProps) {
  const notice = counter && ruleNotice(counter);
  const other = counter && otherTeamText(counter, teamNumber, leftOut);
  return (
    <section className="half" aria-label="Counter team">
      <h2 className="half-title">Counter team</h2>
      {other && (
        <p className="other-team">
          {other}{" "}
          <button type="button" className="link-button" onClick={onBestTeam}>
            Back to the best team
          </button>
        </p>
      )}
      {counter ? (
        <CounterSlots picks={counter.picks} pokemonById={pokemonById} />
      ) : (
        <div className={`counter-empty${error ? " counter-error" : ""}`}>{error ?? "No counter team yet"}</div>
      )}
      <p className="visually-hidden counter-live" aria-live="polite">
        {announcement(counter, other, error)}
      </p>
      {notice && <p className="counter-notice">{notice}</p>}
    </section>
  );
}
