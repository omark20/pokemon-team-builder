// The grid section: the controls, then the matching Pokémon as cards. The
// whole list is in memory; cards are drawn 60 at a time, and a button under
// them draws the next 60, so the page never builds 1,351 cards at once.
import { useMemo, useState } from "react";
import { filterPokemon, listedPokemon, NO_FILTERS, type GridFilters } from "../search";
import type { Pokemon } from "../types";
import { GridControls } from "./GridControls";
import { PokemonCard } from "./PokemonCard";

const PAGE_SIZE = 60;

interface GridProps {
  pokemon: Pokemon[];
  // Adds a Pokémon to the team being edited; resolves to true when it was added.
  onAdd: (pokemon: Pokemon) => Promise<boolean>;
}

const count = (value: number) => value.toLocaleString("en-US");

// Draws the first cards of `pokemon`, and the next batch each time the button
// under them is pressed. The button stays where focus is, so pressing it again
// needs no moving about; the new cards come before it, in reading order. When
// every card is drawn the button goes.
function CardList({ pokemon, onAdd }: GridProps) {
  const [drawn, setDrawn] = useState(PAGE_SIZE);
  const shown = Math.min(drawn, pokemon.length);
  const next = Math.min(PAGE_SIZE, pokemon.length - shown);
  return (
    <>
      <div className="grid">
        {pokemon.slice(0, shown).map((entry) => (
          <PokemonCard key={entry.id} pokemon={entry} onAdd={onAdd} />
        ))}
      </div>
      {next > 0 && (
        <div className="show-more">
          <p aria-live="polite">
            {count(shown)} of {count(pokemon.length)} on screen
          </p>
          <button type="button" onClick={() => setDrawn(shown + PAGE_SIZE)}>
            Show {next} more
          </button>
        </div>
      )}
    </>
  );
}

function NoResults({ query, onClear }: { query: string; onClear: () => void }) {
  const wanted = query.trim();
  return (
    <div className="notice">
      <strong>No Pokémon match{wanted && ` "${wanted}"`}</strong>
      <p>Check the spelling or clear the filters.</p>
      <button type="button" onClick={onClear}>
        Clear filters
      </button>
    </div>
  );
}

export function PokemonGrid({ pokemon, onAdd }: GridProps) {
  const [filters, setFilters] = useState<GridFilters>(NO_FILTERS);
  const visible = useMemo(() => filterPokemon(pokemon, filters), [pokemon, filters]);
  const total = useMemo(() => listedPokemon(pokemon).length, [pokemon]);

  // Enter in the search box adds the best match. The box is cleared only if
  // the Pokémon was added and the reader has not typed something else since.
  async function addTopResult() {
    const top = visible[0];
    if (!top || !(await onAdd(top))) return;
    setFilters((current) => (current.query === filters.query ? { ...current, query: "" } : current));
  }

  return (
    <>
      <GridControls
        filters={filters}
        onChange={setFilters}
        onEnter={addTopResult}
        shown={visible.length}
        total={total}
      />
      {visible.length === 0 ? (
        <NoResults query={filters.query} onClear={() => setFilters(NO_FILTERS)} />
      ) : (
        <CardList key={JSON.stringify(filters)} pokemon={visible} onAdd={onAdd} />
      )}
    </>
  );
}

// Grey cards in the grid's shape, shown until the list arrives.
export function GridPlaceholder() {
  return (
    <div className="grid" aria-busy="true" aria-label="Loading Pokémon">
      {Array.from({ length: 12 }, (_, index) => (
        <div key={index} className="card card-placeholder" />
      ))}
    </div>
  );
}
