// The right half of the face-off card: the counter team, three per row, each
// counter in the same position as the team member it answers, with a short
// line saying how their fight ends. Before a team is built it is an empty
// dashed box. When the team breaks the shared-weakness rule, one notice says so
// here, where it is seen without opening the details.
import { typeStyle } from "../colours";
import { OUTCOME_CLASS } from "../outcomes";
import { ruleNotice } from "../ruleNotice";
import { displayName, type CounterPick, type CounterResult, type Pokemon } from "../types";
import { Sprite } from "./Sprite";

interface CounterProps {
  counter: CounterResult | null;
  error: string | null; // why the last build gave no team; shown in the empty box
  pokemonById: Map<number, Pokemon>;
}

// "beats Charizard", "draws with Venusaur" or "loses to Blastoise".
function resultChip(pick: CounterPick): string {
  const verb = pick.outcome === "wins" ? "beats" : pick.outcome;
  return `${verb} ${displayName(pick.opponent.name)}`;
}

export function CounterHalf({ counter, error, pokemonById }: CounterProps) {
  const notice = counter && ruleNotice(counter);
  return (
    <section className="half" aria-label="Counter team">
      <h2 className="half-title">Counter team</h2>
      {counter ? (
        <ol className="slots">
          {counter.picks.map((pick, index) => {
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
      ) : (
        <div className={`counter-empty${error ? " counter-error" : ""}`}>
          {error ?? "No counter team yet"}
        </div>
      )}
      <p className="visually-hidden counter-live" aria-live="polite">
        {counter ? `Counter team ready: ${counter.picks.map((pick) => displayName(pick.counter.name)).join(", ")}.` : error}
      </p>
      {notice && <p className="counter-notice">{notice}</p>}
    </section>
  );
}
