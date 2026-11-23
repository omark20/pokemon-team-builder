// Every counter against every one of the visitor's Pokémon: a tick where the
// counter wins, a cross where it loses, a dash for a draw, and the opponent it
// was picked for outlined. Each mark is a button named with its words, which
// also show under the table when it is pressed or focused, because a title
// does not show on a phone.
import { useState } from "react";
import { OUTCOME_CLASS, OUTCOME_MARK, OUTCOME_WORD, turnCount, turnsWord } from "../outcomes";
import { displayName, type CounterResult, type FightCell } from "../types";

// Column widths in pixels: the counters' names, then each mark and the wins count.
// The table is never narrower than these, and scrolls inside its box instead.
const NAME_COLUMN = 104;
const MARK_COLUMN = 56;

// "Corviknight wins: 1 turn against 7", the counter's turns first.
function cellWords(counterName: string, cell: FightCell): string {
  const { outcome, counter_turns: ours, opponent_turns: theirs } = cell;
  return `${displayName(counterName)} ${OUTCOME_WORD[outcome]}: ${turnCount(ours)} ${turnsWord(ours)} against ${turnCount(theirs)}`;
}

interface RowProps {
  name: string; // the counter's
  row: FightCell[];
  own: number; // the column of the opponent it was picked for
  onShow: (words: string) => void;
}

function FightRow({ name, row, own, onShow }: RowProps) {
  const wins = row.filter((cell) => cell.outcome === "wins").length;
  return (
    <tr>
      <th scope="row">{displayName(name)}</th>
      {row.map((cell, column) => {
        const words = cellWords(name, cell);
        return (
          <td key={column} className={`fight ${OUTCOME_CLASS[cell.outcome]}${column === own ? " own" : ""}`}>
            <button type="button" aria-label={words} title={words} onClick={() => onShow(words)} onFocus={() => onShow(words)}>
              {OUTCOME_MARK[cell.outcome]}
            </button>
          </td>
        );
      })}
      <td className="fight-total">
        wins {wins} of {row.length}
      </td>
    </tr>
  );
}

export function FightTable({ counter }: { counter: CounterResult }) {
  const [shown, setShown] = useState<string | null>(null);
  const opponents = counter.picks.map((pick) => pick.opponent.name);
  return (
    <>
      <div className="fights-scroll">
        <table className="fights" style={{ minWidth: NAME_COLUMN + (opponents.length + 1) * MARK_COLUMN }}>
          <colgroup>
            <col style={{ width: NAME_COLUMN }} />
          </colgroup>
          <thead>
            <tr>
              <th scope="col">Counter</th>
              {opponents.map((name, column) => (
                <th key={column} scope="col">
                  {displayName(name)}
                </th>
              ))}
              <th scope="col">Wins</th>
            </tr>
          </thead>
          <tbody>
            {counter.grid.map((row, index) => (
              <FightRow key={index} name={counter.picks[index]!.counter.name} row={row} own={index} onShow={setShown} />
            ))}
          </tbody>
        </table>
      </div>
      <p className="fight-words">{shown ?? "Tap or focus a mark to read it in words."}</p>
    </>
  );
}
