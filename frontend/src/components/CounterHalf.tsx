// The right half of the face-off card: the counter team, three per row, each
// counter in the same position as the team member it answers, with a short
// "beats X" line. Before a team is built it is an empty dashed box. The two
// notices that limit what the result claims are shown here, not hidden in
// the details.
import { typeStyle } from "../colours";
import { displayName, type CounterResult, type Pokemon } from "../types";
import { Sprite } from "./Sprite";

export const NOTICES = {
  stoppedEarly: "The search hit its step limit. This is the best team found; a better one may exist.",
  relaxed:
    "No team avoids a shared weakness here, so the rule was loosened: more than half of this team is weak to one of your types.",
};

interface CounterProps {
  counter: CounterResult | null;
  error: string | null; // why the last build gave no team; shown in the empty box
  pokemonById: Map<number, Pokemon>;
}

export function CounterHalf({ counter, error, pokemonById }: CounterProps) {
  return (
    <section className="half" aria-label="Counter team">
      <h2 className="half-title">Counter team</h2>
      {counter ? (
        <ol className="slots">
          {counter.picks.map(({ counter: pick, opponent }, index) => {
            const known = pokemonById.get(pick.id);
            const name = displayName(pick.name);
            return (
              <li key={index} className="slot" style={known && typeStyle(known.types[0]!)}>
                <Sprite url={known?.sprite_url ?? null} name={name} size={48} />
                <span className="slot-name">{name}</span>
                <span className="beats">beats {displayName(opponent.name)}</span>
              </li>
            );
          })}
        </ol>
      ) : (
        <div className={`counter-empty${error ? " counter-error" : ""}`} role={error ? "alert" : undefined}>
          {error ?? "No counter team yet"}
        </div>
      )}
      {counter?.stopped_early && <p className="counter-notice">{NOTICES.stoppedEarly}</p>}
      {counter?.relaxed && <p className="counter-notice">{NOTICES.relaxed}</p>}
    </section>
  );
}
