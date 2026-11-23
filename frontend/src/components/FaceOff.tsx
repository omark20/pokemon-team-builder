// The face-off card: team tabs on top, then the selected team on the left
// facing its counter team on the right, then "Show details" once a counter
// team exists, and a footer row with a status line and the buttons.
import { useRef, useState } from "react";
import { fetchMoves } from "../api";
import type { TeamStore } from "../teamStore";
import { MOST_TEAMS, type TeamsState } from "../teamsState";
import type { CounterResult, Pokemon, SlotMoves, Team } from "../types";
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
const LEAVE_OUT_LABEL = "Leave out legendary and mythical Pokémon";

function statusLine(team: Team, counter: CounterResult | null): string {
  if (counter) {
    const pool = counter.pool_size.toLocaleString("en-US");
    const leftOut = counter.legendary_left_out ? ", legendary and mythical left out" : "";
    if (counter.picks.length === 0) return `Searched ${pool} candidates${leftOut}.`; // no team among them
    return `Best team out of ${pool} candidates${leftOut}.`;
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

// The row along the bottom of the card. Building needs at least one member;
// once a team is shown the button offers another, until there is none or ten
// have been shown.
function Footer({ store, teams, team }: Pick<FaceOffProps, "store" | "teams"> & { team: Team }) {
  const shown = teams.counter;
  const noMore = shown !== null && (shown.picks.length === 0 || teams.teamNumber >= MOST_TEAMS);
  return (
    <footer className="face-off-footer">
      <p className="face-off-status">{statusLine(team, shown)}</p>
      <LegendaryToggle store={store} teams={teams} />
      {shown?.picks.length ? (
        <button type="button" disabled={teams.creating} onClick={() => void store.saveCounterAsTeam()}>
          Save as new team
        </button>
      ) : null}
      <button
        type="button"
        className="primary"
        disabled={team.pokemon_ids.length === 0 || teams.building || noMore}
        onClick={() => void (shown ? store.showAnotherTeam() : store.buildCounter())}
      >
        {shown ? "Show another team" : "Build counter team"}
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

// After a delete the deleted team's controls are gone: focus the tab now
// selected, or "New team" when no team is left.
function focusSelectedTab(card: HTMLElement | null) {
  card?.querySelector<HTMLElement>('.tab[aria-pressed="true"], .tab-new')?.focus();
}

// "Show details" under a counter team, and the details it opens. The open state
// belongs to one result, so a new result starts closed.
function DetailsPanel({ counter, chosen }: { counter: CounterResult; chosen: SlotMoves[] }) {
  const [openFor, setOpenFor] = useState<CounterResult | null>(null);
  const open = openFor === counter;
  return (
    <>
      <button type="button" className="details-toggle" aria-expanded={open} onClick={() => setOpenFor(open ? null : counter)}>
        {open ? "Hide details" : "Show details"}
      </button>
      {open && <CounterDetails counter={counter} chosen={chosen} />}
    </>
  );
}

export function FaceOff({ store, teams, pokemonById, alertTeamIds }: FaceOffProps) {
  const card = useRef<HTMLElement>(null);
  if (teams.status !== "ready") {
    return (
      <section className="face-off">
        <TeamsUnavailable teams={teams} store={store} />
      </section>
    );
  }
  const team = store.activeTeam();
  const { counter } = teams;
  return (
    <section ref={card} className="face-off" aria-label="Team and counter team">
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
              onMembers={(members) => store.setMembers(team.id, members)}
              onMoves={(slot, moves) => store.setMoves(team.id, slot, moves)}
              loadMoves={fetchMoves}
              onRename={(name) => void store.rename(team.id, name)}
              onDelete={() => void store.remove(team.id).then(() => focusSelectedTab(card.current))}
            />
            <span className="versus" aria-hidden="true">
              vs
            </span>
            <CounterHalf
              counter={counter}
              error={teams.counterError}
              pokemonById={pokemonById}
              teamNumber={teams.teamNumber}
              leftOut={teams.leftOut.length}
              onBestTeam={() => void store.buildCounter()}
            />
          </div>
          {counter?.picks.length ? <DetailsPanel counter={counter} chosen={team.moves} /> : null}
          <Footer store={store} teams={teams} team={team} />
        </>
      )}
    </section>
  );
}
