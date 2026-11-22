// The right half of the face-off card: the counter team, three per row, each
// counter in the same position as the team member it answers, with a short
// "beats X" line and a "Why?" button that shows the reason for that pick
// under the card. Before a team is built it is an empty dashed box. The two
// notices that limit what the result claims are shown here, not hidden in
// the details.
import { useState } from "react";
import { typeStyle } from "../colours";
import { displayName, type CounterPick, type CounterResult, type Pokemon } from "../types";
import { Sprite } from "./Sprite";

export const NOTICES = {
  stoppedEarly: "The search hit its step limit. This is the best team found. A better one may exist.",
  relaxed:
    "No team avoids a shared weakness here, so the rule was loosened: more than half of this team is weak to one of your types.",
};

interface CounterProps {
  counter: CounterResult | null;
  error: string | null; // why the last build gave no team; shown in the empty box
  pokemonById: Map<number, Pokemon>;
}

interface CardProps {
  pick: CounterPick;
  slot: number;
  known: Pokemon | undefined; // the counter's entry in the list, for its picture and colour
  open: boolean;
  onToggle: () => void;
}

function CounterCard({ pick, slot, known, open, onToggle }: CardProps) {
  const name = displayName(pick.counter.name);
  const reasonId = `counter-why-${slot}`;
  return (
    <li className="slot" style={known && typeStyle(known.types[0]!)}>
      <Sprite url={known?.sprite_url ?? null} name={name} size={48} />
      <span className="slot-name">{name}</span>
      <span className="beats">beats {displayName(pick.opponent.name)}</span>
      <button type="button" className="why-toggle" aria-expanded={open} aria-controls={reasonId} onClick={onToggle}>
        {open ? "Hide why" : "Why?"}
      </button>
      {open && (
        <p id={reasonId} className="why">
          {pick.reason}
        </p>
      )}
    </li>
  );
}

// Which cards show their reason. It belongs to one result, so a new result
// (another team, a change, a rebuild) starts with every reason hidden.
function useOpenReasons(counter: CounterResult | null) {
  const [open, setOpen] = useState<{ result: CounterResult | null; slots: Set<number> }>({ result: null, slots: new Set() });
  const slots = open.result === counter ? open.slots : new Set<number>();
  // Built from the latest state, so quick presses on several cards all count.
  function toggle(slot: number) {
    setOpen((current) => {
      const next = new Set(current.result === counter ? current.slots : []);
      if (!next.delete(slot)) next.add(slot);
      return { result: counter, slots: next };
    });
  }
  return { isOpen: (slot: number) => slots.has(slot), toggle };
}

export function CounterHalf({ counter, error, pokemonById }: CounterProps) {
  const reasons = useOpenReasons(counter);
  return (
    <section className="half" aria-label="Counter team">
      <h2 className="half-title">Counter team</h2>
      {counter ? (
        <ol className="slots">
          {counter.picks.map((pick, slot) => (
            <CounterCard
              key={slot}
              pick={pick}
              slot={slot}
              known={pokemonById.get(pick.counter.id)}
              open={reasons.isOpen(slot)}
              onToggle={() => reasons.toggle(slot)}
            />
          ))}
        </ol>
      ) : (
        <div className={`counter-empty${error ? " counter-error" : ""}`}>
          {error ?? "No counter team yet"}
        </div>
      )}
      <p className="visually-hidden counter-live" aria-live="polite">
        {counter ? `Counter team ready: ${counter.picks.map((pick) => displayName(pick.counter.name)).join(", ")}.` : error}
      </p>
      {counter?.stopped_early && <p className="counter-notice">{NOTICES.stoppedEarly}</p>}
      {counter?.relaxed && <p className="counter-notice">{NOTICES.relaxed}</p>}
    </section>
  );
}
