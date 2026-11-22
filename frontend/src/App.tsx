// The one screen of the app: the face-off card with the visitor's teams, then
// the grid of every Pokémon. The Pokémon list and the teams are each loaded
// once when the page opens.
import { useEffect, useMemo, useState } from "react";
import { fetchPokemon } from "./api";
import { FaceOff } from "./components/FaceOff";
import { GridPlaceholder, PokemonGrid } from "./components/PokemonGrid";
import { TeamStore, useTeams, type Notice } from "./teamStore";
import type { Pokemon } from "./types";

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

// The result of the last thing the visitor did, kept in view at the bottom of
// the window, since the grid's Add buttons may be far below the team.
function NoticeBar({ notice, onClose }: { notice: Notice | null; onClose: () => void }) {
  if (!notice) return null;
  return (
    <div className={`notice-bar notice-${notice.kind}`} role={notice.kind === "error" ? "alert" : "status"}>
      <span>{notice.text}</span>
      <button type="button" className="notice-close" aria-label="Close message" onClick={onClose}>
        ×
      </button>
    </div>
  );
}

const NOT_LOADED: Pokemon[] = [];

export default function App() {
  const { state, retry } = usePokemonList();
  const [store] = useState(() => new TeamStore());
  const teams = useTeams(store);
  useEffect(() => void store.load(), [store]);
  const pokemon = state.status === "ready" ? state.pokemon : NOT_LOADED;
  const pokemonById = useMemo(() => new Map(pokemon.map((entry) => [entry.id, entry])), [pokemon]);
  const addToTeam = (entry: Pokemon) => store.add(entry);
  return (
    <main className="page">
      <h1>Pokémon Team Builder</h1>
      <FaceOff store={store} teams={teams} pokemonById={pokemonById} />
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
      {state.status === "ready" && <PokemonGrid pokemon={state.pokemon} onAdd={addToTeam} />}
      <NoticeBar notice={teams.notice} onClose={() => store.dismissNotice()} />
    </main>
  );
}
