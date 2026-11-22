// The controls above the grid: a search box, a type filter, the checkbox that
// hides special versions, and how many cards are on screen out of how many match.
import type { KeyboardEvent } from "react";
import type { GridFilters } from "../search";
import { TYPE_NAMES, type TypeName } from "../types";

interface ControlsProps {
  filters: GridFilters;
  onChange: (filters: GridFilters) => void;
  // Called when Enter is pressed in a search box that holds a query.
  onEnter: () => void;
  onScreen: number; // cards drawn so far
  matching: number; // entries that pass the search and both filters
}

const count = (value: number) => value.toLocaleString("en-US");

export function GridControls({ filters, onChange, onEnter, onScreen, matching }: ControlsProps) {
  function handleKey(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "Enter" && filters.query.trim() !== "") onEnter();
  }
  return (
    <section className="controls" aria-label="Search and filters">
      <input
        type="search"
        className="controls-search"
        aria-label="Search by name or number"
        placeholder="Search by name or number"
        value={filters.query}
        onChange={(event) => onChange({ ...filters, query: event.target.value })}
        onKeyDown={handleKey}
      />
      <select
        aria-label="Type"
        value={filters.type}
        onChange={(event) => onChange({ ...filters, type: event.target.value as TypeName | "" })}
      >
        <option value="">All types</option>
        {TYPE_NAMES.map((type) => (
          <option key={type} value={type}>
            {type}
          </option>
        ))}
      </select>
      <label className="controls-check">
        <input
          type="checkbox"
          checked={filters.hideSpecial}
          onChange={(event) => onChange({ ...filters, hideSpecial: event.target.checked })}
        />
        Hide special versions (Mega, regional and others)
      </label>
      <p className="controls-count" role="status">
        Showing {count(onScreen)} of {count(matching)}
      </p>
    </section>
  );
}
