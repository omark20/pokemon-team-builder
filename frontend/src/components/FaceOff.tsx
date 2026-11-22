// The face-off card: team tabs on top, then the selected team on the left
// facing its counter team on the right, then a footer with a status line.
import type { TeamStore, TeamsState } from "../teamStore";
import type { Pokemon, Team } from "../types";
import { TeamHalf } from "./TeamHalf";
import { TeamTabs } from "./TeamTabs";

interface FaceOffProps {
  store: TeamStore;
  teams: TeamsState;
  pokemonById: Map<number, Pokemon>;
}

function statusLine(team: Team): string {
  return team.pokemon_ids.length === 0
    ? "Add Pokémon from the grid below."
    : "Drag to reorder. Hover a Pokémon to remove it.";
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

export function FaceOff({ store, teams, pokemonById }: FaceOffProps) {
  if (teams.status !== "ready") {
    return (
      <section className="face-off">
        <TeamsUnavailable teams={teams} store={store} />
      </section>
    );
  }
  const team = store.activeTeam();
  return (
    <section className="face-off" aria-label="Team and counter team">
      <TeamTabs
        teams={teams.teams}
        activeId={teams.activeId}
        creating={teams.creating}
        onSelect={(id) => store.select(id)}
        onNew={() => void store.newTeam()}
      />
      {team ? (
        <>
          <div className="halves">
            <TeamHalf
              team={team}
              pokemonById={pokemonById}
              onMembers={(ids) => store.setMembers(team.id, ids)}
              onRename={(name) => void store.rename(team.id, name)}
              onDelete={() => void store.remove(team.id)}
            />
            <span className="versus" aria-hidden="true">
              vs
            </span>
            <section className="half" aria-label="Counter team">
              <h2 className="half-title">Counter team</h2>
              <div className="counter-empty">No counter team yet</div>
            </section>
          </div>
          <footer className="face-off-footer">
            <p className="face-off-status">{statusLine(team)}</p>
          </footer>
        </>
      ) : (
        <FirstVisit />
      )}
    </section>
  );
}
