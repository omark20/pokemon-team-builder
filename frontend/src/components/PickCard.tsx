// One pick as a scoreboard: the counter on the left and the opponent it was
// picked for on the right, each with the turns it needs to knock the other out
// and the move it uses. The winner's half is tinted green; a draw tints neither.
// "Why?" shows the numbers behind the result in a block under the card's row.
import { useState } from "react";
import { turnCount, turnsWord } from "../outcomes";
import { displayName, moveName, type CounterPick, type FightSide } from "../types";

function Fighter({ side, won }: { side: FightSide; won: boolean }) {
  return (
    <div className={won ? "fighter outcome-win" : "fighter"}>
      <span className="fighter-name">{displayName(side.name)}</span>
      <span className="fighter-turns">
        <strong>{turnCount(side.turns)}</strong> {turnsWord(side.turns)}
      </span>
      <span className="fighter-move">{side.move ? moveName(side.move) : "No damaging move"}</span>
    </div>
  );
}

// The open state lives here, so it starts closed whenever the details are
// opened again; a new counter team always closes the details first.
export function PickCard({ pick, slot }: { pick: CounterPick; slot: number }) {
  const [open, setOpen] = useState(false);
  const reasonId = `pick-why-${slot}`;
  return (
    <>
      <article className="pick-card">
        <p className="visually-hidden">{pick.line}.</p>
        <div className="scoreboard">
          <Fighter side={pick.counter} won={pick.outcome === "wins"} />
          <span className="scoreboard-vs" aria-hidden="true">
            vs
          </span>
          <Fighter side={pick.opponent} won={pick.outcome === "loses to"} />
        </div>
        <button type="button" className="why-toggle" aria-expanded={open} aria-controls={reasonId} onClick={() => setOpen(!open)}>
          {open ? "Hide why" : "Why?"}
        </button>
      </article>
      {open && (
        <p id={reasonId} className="pick-why">
          {pick.reason}
        </p>
      )}
    </>
  );
}
