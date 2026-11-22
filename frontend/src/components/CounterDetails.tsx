// What "Show details" opens under the face-off: the view of the team as a
// whole. How the team was chosen, each pick with its matchup, every counter's
// matchup against every member of the team, the team's three totals, and how
// many counters each of the team's types hits hard. The sentence saying why a
// counter was picked is on its own card, behind "Why?".
//
// A matchup is how hard the counter hits that Pokémon minus how hard it is
// hit back, in points (one per doubling of damage), from -5 to 5. A counter's
// coverage is its row of the table added up.
import { matchupStyle, matchupWord, signed } from "../matchupWords";
import { displayName, type CounterResult } from "../types";


// The scoring is this app's own, not the game's, so it is explained first.
// The points follow the counter core's table: 4× +2, 2× +1, 1× 0, ½× -1, ¼× -2, no effect -3.
export const HOW_CHOSEN = [
  "Best matchup against its own opponent first, then against your whole team, then base stats. No Pokémon twice, and no type of yours may hit more than half the counters hard.",
  "Points are ours: one per doubling of damage, given minus taken. 4× is +2, 2× is +1, 1× is 0, ½× is -1, ¼× is -2, and no effect is -3.",
];

function HowChosen() {
  return (
    <section className="how-chosen" aria-labelledby="how-chosen-title">
      <h3 id="how-chosen-title">How this team was chosen</h3>
      {HOW_CHOSEN.map((text) => (
        <p key={text}>{text}</p>
      ))}
    </section>
  );
}

// A matchup as a word and its number: "Strong +3", "Weak -1".
function Matchup({ points }: { points: number }) {
  return (
    <>
      <span className="matchup-word">{matchupWord(points)}</span> {signed(points)}
    </>
  );
}

// Each pick on one line: "Rhyperior beats Charizard", then its matchup.
function PickList({ counter }: { counter: CounterResult }) {
  return (
    <ul className="pick-list">
      {counter.picks.map((pick, index) => (
        <li key={index}>
          <strong>{displayName(pick.counter.name)}</strong> <span className="muted">beats</span>{" "}
          <strong>{displayName(pick.opponent.name)}</strong>{" "}
          <span className="matchup" style={matchupStyle(pick.matchup)}>
            <Matchup points={pick.matchup} />
          </span>
        </li>
      ))}
    </ul>
  );
}

// The narrowest a column may get before the table scrolls inside its box
// instead: enough for "Strong" above its number.
const MIN_COLUMN_WIDTH = 50;

// Each cell carries its word and number; the colour, greener the stronger,
// only repeats them.
function MatchupTable({ counter }: { counter: CounterResult }) {
  return (
    // On a narrow screen the table scrolls sideways inside its own box, never the page.
    <div className="matchups-scroll">
      <table className="matchups" style={{ minWidth: (counter.picks.length + 2) * MIN_COLUMN_WIDTH }}>
        <caption>Every counter against every one of your Pokémon</caption>
        <thead>
          <tr>
            <th scope="col">Counter</th>
            {counter.picks.map((pick, index) => (
              <th key={index} scope="col" title={displayName(pick.opponent.name)}>
                {displayName(pick.opponent.name)}
              </th>
            ))}
            <th scope="col">Coverage</th>
          </tr>
        </thead>
        <tbody>
          {counter.grid.map((row, index) => (
            <tr key={index}>
              <th scope="row" title={displayName(counter.picks[index]!.counter.name)}>
                {displayName(counter.picks[index]!.counter.name)}
              </th>
              {row.map((value, column) => (
                <td key={column} className="matchup-cell" style={matchupStyle(value)}>
                  <Matchup points={value} />
                </td>
              ))}
              <td className="row-sum">{signed(row.reduce((sum, value) => sum + value, 0))}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Totals({ counter }: { counter: CounterResult }) {
  const { totals, weakness_counts: weak } = counter;
  const weaknesses = Object.entries(weak).map(([type, count]) => `${type} ${count}`);
  return (
    <>
      <dl className="totals">
        <dt>Matchup points against assigned opponents</dt>
        <dd>{signed(totals.assigned_points)}</dd>
        <dt>Coverage, all matchups added up</dt>
        <dd>{signed(totals.coverage)}</dd>
        <dt>Base stats, added up</dt>
        <dd>{totals.base_stats.toLocaleString("en-US")}</dd>
      </dl>
      <p className="weaknesses">Counters each of your types hits for 2× or more: {weaknesses.join(", ")}.</p>
    </>
  );
}

export function CounterDetails({ counter }: { counter: CounterResult }) {
  return (
    <div className="counter-details">
      <HowChosen />
      <PickList counter={counter} />
      <MatchupTable counter={counter} />
      <Totals counter={counter} />
    </div>
  );
}
