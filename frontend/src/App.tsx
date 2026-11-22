// The one screen of the app: change alerts, the face-off card with the
// visitor's teams, the grid of every Pokémon, and when PokéAPI was last
// checked. The list, the teams, the alerts and the scan status are each read
// once when the page opens.
import { useEffect, useMemo, useState } from "react";
import { fetchPokemon } from "./api";
import { touchesTeams } from "./alertText";
import { useAlerts } from "./alerts";
import { AlertPanel, PAGE_TITLE_ID } from "./components/AlertPanel";
import { FaceOff } from "./components/FaceOff";
import { NoticeBar } from "./components/NoticeBar";
import { GridPlaceholder, PokemonGrid } from "./components/PokemonGrid";
import { StatusFooter } from "./components/StatusFooter";
import { TEAM_SIZE } from "./teamMoves";
import { TeamStore, useTeams } from "./teamStore";
import type { Pokemon, Team } from "./types";

type ListState =
  | { status: "loading" }
  | { status: "failed" }
  | { status: "ready"; pokemon: Pokemon[] };

// Loads the list when the page opens, and again each time `retry` is called.
function usePokemonList() {
  const [state, setState] = useState<ListState>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let current = true;
    fetchPokemon().then(
      (pokemon) => current && setState({ status: "ready", pokemon }),
      () => current && setState({ status: "failed" }),
    );
    return () => {
      current = false;
    };
  }, [attempt]);

  function retry() {
    setState({ status: "loading" });
    setAttempt((count) => count + 1);
  }
  return { state, retry };
}

const NOT_LOADED: Pokemon[] = [];

// The alerts that still touch a team, and the teams that get a tab dot.
function useTeamAlerts(teams: Team[]) {
  const alerts = useAlerts();
  const shown = alerts.alerts.filter((alert) => touchesTeams(alert, teams));
  const flagged = teams.filter((team) => shown.some((alert) => touchesTeams(alert, [team])));
  return { ...alerts, shown, alertTeamIds: new Set(flagged.map((team) => team.id)) };
}

export default function App() {
  const { state, retry } = usePokemonList();
  const [store] = useState(() => new TeamStore());
  const teams = useTeams(store);
  useEffect(() => void store.load(), [store]);
  const pokemon = state.status === "ready" ? state.pokemon : NOT_LOADED;
  const pokemonById = useMemo(() => new Map(pokemon.map((entry) => [entry.id, entry])), [pokemon]);
  const addToTeam = (entry: Pokemon) => store.add(entry);
  const teamFull = (store.activeTeam()?.pokemon_ids.length ?? 0) >= TEAM_SIZE;
  const alerts = useTeamAlerts(teams.teams);
  return (
    <main className="page">
      {/* Focus comes here when what had it goes away (the last alert dismissed). */}
      <h1 id={PAGE_TITLE_ID} tabIndex={-1}>Pokémon Team Builder</h1>
      <AlertPanel
        {...alerts}
        alerts={alerts.shown}
        teams={teams.teams}
        pokemonById={pokemonById}
        onDismiss={(id) => void alerts.dismiss(id)}
        onDismissAll={() => void alerts.dismissAll(alerts.shown.map((alert) => alert.id))}
        onRetry={() => void alerts.load()}
      />
      <FaceOff store={store} teams={teams} pokemonById={pokemonById} alertTeamIds={alerts.alertTeamIds} />
      {state.status === "loading" && <GridPlaceholder />}
      {state.status === "failed" && (
        <div className="notice" role="alert">
          <strong>Couldn't load Pokémon</strong>
          <p>Check your connection and try again.</p>
          <button type="button" onClick={retry}>
            Try again
          </button>
        </div>
      )}
      {state.status === "ready" && <PokemonGrid pokemon={state.pokemon} onAdd={addToTeam} teamFull={teamFull} />}
      <StatusFooter />
      <NoticeBar notice={teams.notice} onClose={() => store.dismissNotice()} />
    </main>
  );
}
