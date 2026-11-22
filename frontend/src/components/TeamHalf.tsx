// The left half of the face-off card: the selected team as six positions,
// three per row. Filled positions are TeamSlots; the rest are outlines, and a
// slot dropped on an outline moves to the end, since a team has no gaps.
import { useRef, useState, type FormEvent } from "react";
import { flushSync } from "react-dom";
import { moveToEnd, removeSlot, swapSlots, TEAM_SIZE } from "../teamMoves";
import type { Pokemon, Team } from "../types";
import { TeamSlot } from "./TeamSlot";

interface HalfProps {
  team: Team;
  pokemonById: Map<number, Pokemon>;
  onMembers: (pokemonIds: number[]) => void;
  onRename: (name: string) => void;
  onDelete: () => void;
}

// Name, count, and Rename and Delete for the selected team. Rename turns the
// name into a text box; Delete asks first.
function TeamHeader({ team, onRename, onDelete }: Omit<HalfProps, "pokemonById" | "onMembers">) {
  const [editing, setEditing] = useState(false);
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const name = String(new FormData(event.currentTarget).get("name")).trim();
    if (name !== "" && name !== team.name) onRename(name);
    setEditing(false);
  }
  if (editing) {
    return (
      <form className="half-header" onSubmit={submit}>
        <input name="name" aria-label="Team name" defaultValue={team.name} maxLength={50} autoFocus />
        <button type="submit">Save</button>
        <button type="button" onClick={() => setEditing(false)}>
          Cancel
        </button>
      </form>
    );
  }
  const confirmDelete = () => window.confirm(`Delete ${team.name}? This cannot be undone.`) && onDelete();
  return (
    <div className="half-header">
      <h2 className="half-title">{team.name}</h2>
      <span className="half-count">{team.pokemon_ids.length} of 6</span>
      <button type="button" className="link-button" onClick={() => setEditing(true)}>
        Rename
      </button>
      <button type="button" className="link-button" onClick={confirmDelete}>
        Delete
      </button>
    </div>
  );
}

// A stand-in for an entry the list does not hold (the list failed to load).
const unknownPokemon = (id: number): Pokemon => ({
  id, name: `Pokémon ${id}`, is_default: true, types: ["normal"], stats: [], sprite_url: null, removed: false,
});

export function TeamHalf({ team, pokemonById, onMembers, onRename, onDelete }: HalfProps) {
  const ids = team.pokemon_ids;
  const dragged = useRef<number | null>(null);
  const list = useRef<HTMLOListElement>(null);
  // A keyboard user keeps their place: after a move or a removal, focus goes
  // to the slot that now holds the moved Pokémon (or took the removed one's
  // place): the same control if it has one, else its other arrow, else its "×".
  function changeAndFocus(next: number[], index: number, control: string) {
    flushSync(() => onMembers(next));
    const slot = list.current?.children[Math.min(index, next.length - 1)];
    const choices = [`.${control}`, ".slot-earlier, .slot-later", ".slot-control"];
    const target = choices.map((selector) => slot?.querySelector<HTMLElement>(selector)).find(Boolean);
    target?.focus();
  }
  const move = (from: number, to: number, control: string) => changeAndFocus(swapSlots(ids, from, to), to, control);
  function dropOn(target: number | "end") {
    const from = dragged.current;
    dragged.current = null;
    if (from === null || from === target) return;
    onMembers(target === "end" ? moveToEnd(ids, from) : swapSlots(ids, from, target));
  }
  return (
    <section className="half" aria-label={team.name}>
      <TeamHeader team={team} onRename={onRename} onDelete={onDelete} />
      <ol className="slots" ref={list}>
        {ids.map((id, index) => (
          <TeamSlot
            key={`${index}-${id}`}
            pokemon={pokemonById.get(id) ?? unknownPokemon(id)}
            onRemove={() => changeAndFocus(removeSlot(ids, index), index, "slot-remove")}
            onMoveEarlier={index > 0 ? () => move(index, index - 1, "slot-earlier") : undefined}
            onMoveLater={index < ids.length - 1 ? () => move(index, index + 1, "slot-later") : undefined}
            onDragStart={() => (dragged.current = index)}
            onDrop={() => dropOn(index)}
          />
        ))}
        {Array.from({ length: TEAM_SIZE - ids.length }, (_, index) => (
          <li
            key={`empty-${index}`}
            className="slot slot-empty"
            onDragOver={(event) => event.preventDefault()}
            onDrop={(event) => {
              event.preventDefault();
              dropOn("end");
            }}
          >
            <span className="slot-outline" />
            <span className="slot-name">Empty</span>
          </li>
        ))}
      </ol>
    </section>
  );
}
