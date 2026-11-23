// Finding a move: a search box and a drop-down of the types this Pokémon has moves
// of narrow the list as the visitor types or chooses. The list is the only part
// that scrolls; its headings stay above it. Each row is one button: pressing it
// adds the move, or removes it if it is in use. With four in use the other rows
// are dimmed and do nothing.
import { useState } from "react";
import { accuracyText, byStrength, classLine, matching, type MoveOption } from "../moveChoice";
import { displayName, moveName } from "../types";

interface ListProps {
  moves: MoveOption[];
  used: number[];
  full: boolean;
  onToggle: (id: number) => void;
}

// A row is read out as "Overheat, Fire, Special · power 130 · 90% accurate, in use".
function MoveRow({ move, used, full, onToggle }: { move: MoveOption; used: boolean; full: boolean; onToggle: (id: number) => void }) {
  const label = `${moveName(move.name)}, ${displayName(move.type)}, ${classLine(move)}${used ? ", in use" : ""}`;
  return (
    <button
      type="button"
      className="move-row"
      aria-label={label}
      aria-pressed={used}
      disabled={full && !used}
      onClick={() => onToggle(move.id)}
    >
      <span>
        {used && "✓ "}
        {moveName(move.name)}
        {used && <span className="move-in-use"> in use</span>}
      </span>
      <span>{displayName(move.type)}</span>
      <span>{displayName(move.damage_class)}</span>
      <span>{move.power}</span>
      <span>{accuracyText(move)}</span>
    </button>
  );
}

export function MoveList({ moves, used, full, onToggle }: ListProps) {
  const [search, setSearch] = useState("");
  const [type, setType] = useState("");
  const types = [...new Set(moves.map((move) => move.type))].sort();
  const shown = byStrength(matching(moves, search, type));
  return (
    <>
      <div className="move-finder">
        <input
          type="search"
          aria-label="Search moves"
          placeholder={`Search ${moves.length} moves`}
          value={search}
          autoFocus
          onChange={(event) => setSearch(event.target.value)}
        />
        <select aria-label="Move type" value={type} onChange={(event) => setType(event.target.value)}>
          <option value="">All types</option>
          {types.map((name) => (
            <option key={name} value={name}>
              {displayName(name)}
            </option>
          ))}
        </select>
      </div>
      {full && <p className="move-full">Four moves in use. Remove one to add another.</p>}
      <div className="move-list-head" aria-hidden="true">
        <span>Move</span>
        <span>Type</span>
        <span>Class</span>
        <span>Power</span>
        <span>Accuracy</span>
      </div>
      <div className="move-list">
        {shown.map((move) => (
          <MoveRow key={move.id} move={move} used={used.includes(move.id)} full={full} onToggle={onToggle} />
        ))}
        {shown.length === 0 && <p>No move matches.</p>}
      </div>
      <p className="move-note">
        Moves that need a charging turn or a special condition, and moves that do no direct damage, are not listed.
      </p>
    </>
  );
}
