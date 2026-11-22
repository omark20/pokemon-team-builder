// The grid section: the controls, then the matching Pokémon as cards. The
// whole list is in memory; cards are drawn 60 at a time, and a button under
// them draws the next 60, so the page never builds 1,351 cards at once.
import { useMemo, useRef, useState } from "react";
import { flushSync } from "react-dom";
import { filterPokemon, NO_FILTERS, type GridFilters } from "../search";
import type { Pokemon } from "../types";
import { GridControls } from "./GridControls";
import { PokemonCard } from "./PokemonCard";

const PAGE_SIZE = 60;

interface GridProps {
  pokemon: Pokemon[];
  // Adds a Pokémon to the team being edited; resolves to true when it was added.
  onAdd: (pokemon: Pokemon) => Promise<boolean>;
  teamFull: boolean; // the team being edited has six members
}

interface CardListProps extends GridProps {
  remaining: number; // matching entries not drawn yet; no button when 0
  onMore: () => void;
}

// The drawn cards, then the button that draws the next batch. The button
// stays where focus is, so pressing it again needs no moving about; the new
// cards come before it, in reading order. The last press removes the button,
// so focus moves to the first card it added.
function CardList({ pokemon, onAdd, teamFull, remaining, onMore }: CardListProps) {
  const grid = useRef<HTMLDivElement>(null);
  const next = Math.min(PAGE_SIZE, remaining);
  function showMore() {
    if (next < remaining) return onMore();
    const firstNew = pokemon.length;
    flushSync(onMore);
    grid.current?.children[firstNew]?.querySelector<HTMLElement>(".card-name")?.focus();
  }
  return (
    <>
      <div className="grid" ref={grid}>
        {pokemon.map((entry) => (
          <PokemonCard key={entry.id} pokemon={entry} onAdd={onAdd} teamFull={teamFull} />
        ))}
      </div>
      {next > 0 && (
        <button type="button" className="show-more" onClick={showMore}>
          Show {next} more
        </button>
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

export function PokemonGrid({ pokemon, onAdd, teamFull }: GridProps) {
  const [filters, setFilters] = useState<GridFilters>(NO_FILTERS);
  const [drawn, setDrawn] = useState(PAGE_SIZE);
  const visible = useMemo(() => filterPokemon(pokemon, filters), [pokemon, filters]);
  const onScreen = Math.min(drawn, visible.length);

  // A new search or filter starts again from the first batch.
  function changeFilters(next: GridFilters) {
    setFilters(next);
    setDrawn(PAGE_SIZE);
  }

  // Enter in the search box adds the best match. The box is cleared only if
  // the Pokémon was added and the reader has not typed something else since.
  async function addTopResult() {
    const top = visible[0];
    if (!top || !(await onAdd(top))) return;
    setFilters((current) => (current.query === filters.query ? { ...current, query: "" } : current));
    setDrawn(PAGE_SIZE);
  }

  return (
    <>
      <GridControls
        filters={filters}
        onChange={changeFilters}
        onEnter={addTopResult}
        onScreen={onScreen}
        matching={visible.length}
      />
      {visible.length === 0 ? (
        <NoResults query={filters.query} onClear={() => changeFilters(NO_FILTERS)} />
      ) : (
        <CardList
          pokemon={visible.slice(0, onScreen)}
          onAdd={onAdd}
          teamFull={teamFull}
          remaining={visible.length - onScreen}
          onMore={() => setDrawn(onScreen + PAGE_SIZE)}
        />
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
