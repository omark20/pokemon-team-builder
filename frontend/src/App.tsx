// The one screen of the app. It loads the Pokémon list once and shows the
// grid, or a loading or error state while there is no list to show.
import { useEffect, useState } from "react";
import { fetchPokemon } from "./api";
import { GridPlaceholder, PokemonGrid } from "./components/PokemonGrid";
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

// Teams arrive with the face-off card; until then nothing can be added.
const addToTeam = async () => false;

export default function App() {
  const { state, retry } = usePokemonList();
  return (
    <main className="page">
      <h1>Pokémon Team Builder</h1>
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
    </main>
  );
}
