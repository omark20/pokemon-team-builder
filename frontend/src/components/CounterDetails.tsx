// What "Show details" opens under the face-off: why each counter was picked,
// every counter's matchup against every member of the team, the team's three
// totals, and how many counters each of the team's types hits hard.
//
// A matchup is how hard the counter hits that Pokémon minus how hard it is
// hit back, in points (one per doubling of damage), from -5 to 5. A counter's
// coverage is its row of the table added up.
import { displayName, type CounterResult } from "../types";

const signed = (value: number) => (value > 0 ? `+${value}` : String(value));
const sign = (value: number) => (value > 0 ? "positive" : value < 0 ? "negative" : "zero");

function Reasons({ counter }: { counter: CounterResult }) {
  return (
    <ul className="reasons">
      {counter.picks.map((pick, index) => (
        <li key={index}>
          <strong>
            {displayName(pick.counter.name)} <span className="muted">beats</span> {displayName(pick.opponent.name)}
          </strong>{" "}
          <span className={`matchup matchup-${sign(pick.matchup)}`}>{signed(pick.matchup)}</span>
          <p>{pick.reason}</p>
        </li>
      ))}
    </ul>
  );
}

// Each cell carries its number; the colour only repeats the sign.
function MatchupTable({ counter }: { counter: CounterResult }) {
  return (
    <table className="matchups">
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
              <td key={column} className={`matchup-${sign(value)}`}>
                {signed(value)}
              </td>
            ))}
            <td className="row-sum">{signed(row.reduce((sum, value) => sum + value, 0))}</td>
          </tr>
        ))}
      </tbody>
    </table>
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
      <Reasons counter={counter} />
      <MatchupTable counter={counter} />
      <Totals counter={counter} />
    </div>
  );
}
