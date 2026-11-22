// The grid section: the controls, then the matching Pokémon as cards. The
// whole list is in memory; cards are drawn 60 at a time as the reader scrolls,
// so the page never builds 1,351 cards at once.
import { useEffect, useMemo, useRef, useState } from "react";
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

// Draws the first cards of `pokemon`, and more each time the marker under the
// last card comes near the bottom of the window.
function CardList({ pokemon, onAdd }: GridProps) {
  const [drawn, setDrawn] = useState(PAGE_SIZE);
  const marker = useRef<HTMLDivElement>(null);
  const hasMore = drawn < pokemon.length;

  // A fresh observer after every batch: a new observer reports at once whether
  // the marker is in view, so a tall window keeps filling until it is not.
  useEffect(() => {
    if (!hasMore || !marker.current) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) setDrawn((count) => count + PAGE_SIZE);
      },
      { rootMargin: "600px" },
    );
    observer.observe(marker.current);
    return () => observer.disconnect();
  }, [hasMore, drawn]);

  return (
    <>
      <div className="grid">
        {pokemon.slice(0, drawn).map((entry) => (
          <PokemonCard key={entry.id} pokemon={entry} onAdd={onAdd} />
        ))}
      </div>
      {hasMore && <div ref={marker} />}
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
