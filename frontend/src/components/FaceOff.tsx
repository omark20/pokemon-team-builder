// The face-off card: team tabs on top, then the selected team on the left
// facing its counter team on the right, then "Show details" once a counter
// team exists, and a footer row with a status line and the buttons.
import { useState } from "react";
import type { TeamStore, TeamsState } from "../teamStore";
import type { CounterResult, Pokemon, Team } from "../types";
import { CounterDetails } from "./CounterDetails";
import { CounterHalf } from "./CounterHalf";
import { TeamHalf } from "./TeamHalf";
import { TeamTabs } from "./TeamTabs";

interface FaceOffProps {
  store: TeamStore;
  teams: TeamsState;
  pokemonById: Map<number, Pokemon>;
  alertTeamIds: Set<number>;
}

// The legendary filter's checkbox label, kept in one place so the wording can
// change without touching the markup.
export const LEAVE_OUT_LABEL = "Leave out legendary and mythical Pokémon";

function statusLine(team: Team, counter: CounterResult | null): string {
  if (counter) {
    const pool = counter.pool_size.toLocaleString("en-US");
    const best = counter.stopped_early ? "Best team found" : "Best team";
    const leftOut = counter.legendary_left_out ? ", legendary and mythical left out" : "";
    return `${best} out of ${pool} candidates${leftOut}.`;
  }
  return team.pokemon_ids.length === 0
    ? "Add Pokémon from the grid below."
    : "Drag a Pokémon to reorder, or select it for its arrows and ×.";
}

// Whether the counter team may include legendary and mythical Pokémon. Off
// when the page opens; changing it clears the counter half.
function LegendaryToggle({ store, teams }: Pick<FaceOffProps, "store" | "teams">) {
  return (
    <label className="legendary-toggle">
      <input
        type="checkbox"
        checked={teams.leaveOutLegendary}
        onChange={(event) => store.setLeaveOutLegendary(event.target.checked)}
      />
      {LEAVE_OUT_LABEL}
    </label>
  );
}

// The row along the bottom of the card. Building needs at least one member.
function Footer({ store, teams, team }: Pick<FaceOffProps, "store" | "teams"> & { team: Team }) {
  return (
    <footer className="face-off-footer">
      <p className="face-off-status">{statusLine(team, teams.counter)}</p>
      <LegendaryToggle store={store} teams={teams} />
      {teams.counter && (
        <button type="button" disabled={teams.creating} onClick={() => void store.saveCounterAsTeam()}>
          Save as new team
        </button>
      )}
      <button
        type="button"
        className="primary"
        disabled={team.pokemon_ids.length === 0 || teams.building}
        onClick={() => void store.buildCounter()}
      >
        {teams.counter ? "Rebuild" : "Build counter team"}
      </button>
    </footer>
  );
}

function FirstVisit() {
  return (
    <div className="first-visit">
      <strong>Build your first team</strong>
      <p>Add a Pokémon from the grid and "Team 1" is created.</p>
    </div>
  );
}

// The card's state while the visitor's teams load, or if they could not.
function TeamsUnavailable({ teams, store }: Pick<FaceOffProps, "teams" | "store">) {
  if (teams.status === "loading") return <p className="face-off-message">Loading your teams…</p>;
  return (
    <div className="face-off-message" role="alert">
      Couldn't load your teams.{" "}
      <button type="button" onClick={() => void store.load()}>
        Try again
      </button>
    </div>
  );
}

export function FaceOff({ store, teams, pokemonById, alertTeamIds }: FaceOffProps) {
  // The result whose details are open; a new result starts closed.
  const [openFor, setOpenFor] = useState<CounterResult | null>(null);
  if (teams.status !== "ready") {
    return (
      <section className="face-off">
        <TeamsUnavailable teams={teams} store={store} />
      </section>
    );
  }
  const team = store.activeTeam();
  const { counter } = teams;
  const open = counter !== null && openFor === counter;
  return (
    <section className="face-off" aria-label="Team and counter team">
      <TeamTabs
        teams={teams.teams}
        activeId={teams.activeId}
        creating={teams.creating}
        alertTeamIds={alertTeamIds}
        onSelect={(id) => store.select(id)}
        onNew={() => void store.newTeam()}
      />
      {!team && <FirstVisit />}
      {team && (
        <>
          <div className="halves">
            <TeamHalf
              key={team.id} // a fresh half per team: an open rename form never moves to another team
              team={team}
              pokemonById={pokemonById}
              onMembers={(ids) => store.setMembers(team.id, ids)}
              onRename={(name) => void store.rename(team.id, name)}
              onDelete={() => void store.remove(team.id)}
            />
            <span className="versus" aria-hidden="true">
              vs
            </span>
            <CounterHalf counter={counter} error={teams.counterError} pokemonById={pokemonById} />
          </div>
          {counter && (
            <button type="button" className="details-toggle" aria-expanded={open} onClick={() => setOpenFor(open ? null : counter)}>
              {open ? "Hide details" : "Show details"}
            </button>
          )}
          {open && <CounterDetails counter={counter} />}
          <Footer store={store} teams={teams} team={team} />
        </>
      )}
    </section>
  );
}
