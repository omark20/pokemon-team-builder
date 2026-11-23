// The left half of the face-off card: the selected team as six positions,
// three per row. Filled positions are TeamSlots; the rest are outlines, and a
// slot dropped on an outline moves to the end, since a team has no gaps. A
// slot's "Moves" opens the move picker for that slot.
import { useEffect, useRef, useState, type FormEvent } from "react";
import { flushSync } from "react-dom";
import type { MoveChoices } from "../moveChoice";
import { editMembers, moveToEnd, removeSlot, swapSlots, TEAM_SIZE } from "../teamMoves";
import type { Members, Pokemon, SlotMoves, Team } from "../types";
import { MovePicker } from "./MovePicker";
import { TeamSlot } from "./TeamSlot";

interface HalfProps {
  team: Team;
  pokemonById: Map<number, Pokemon>;
  onMembers: (members: Members) => void;
  onMoves: (slot: number, moves: SlotMoves) => Promise<boolean>; // true once saved
  loadMoves: (pokemonId: number) => Promise<MoveChoices>;
  onRename: (name: string) => void;
  onDelete: () => void;
}

// Name, count, and Rename and Delete for the selected team. Rename turns the
// name into a text box; Delete asks first.
function TeamHeader({ team, onRename, onDelete }: Pick<HalfProps, "team" | "onRename" | "onDelete">) {
  const [editing, setEditing] = useState(false);
  const renameButton = useRef<HTMLButtonElement>(null);
  const closedForm = useRef(false); // Save or Cancel: focus returns to Rename
  useEffect(() => {
    if (editing || !closedForm.current) return;
    closedForm.current = false;
    renameButton.current?.focus();
  }, [editing]);
  function close() {
    closedForm.current = true;
    setEditing(false);
  }
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const name = String(new FormData(event.currentTarget).get("name")).trim();
    if (name !== "" && name !== team.name) onRename(name);
    close();
  }
  if (editing) {
    return (
      <form className="half-header" onSubmit={submit}>
        <input
          name="name"
          aria-label="Team name"
          defaultValue={team.name}
          maxLength={50}
          autoFocus
          onFocus={(event) => event.target.select()} // typing replaces the old name
        />
        <button type="submit">Save</button>
        <button type="button" onClick={close}>
          Cancel
        </button>
      </form>
    );
  }
  const confirmDelete = () => window.confirm(`Delete ${team.name}? This cannot be undone.`) && onDelete();
  return (
    <div className="half-header">
      <h2 className="half-title">{team.name}</h2>
      <span className="half-count">{team.pokemon_ids.length} of {TEAM_SIZE}</span>
      <button type="button" className="link-button" ref={renameButton} onClick={() => setEditing(true)}>
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

// The unfilled positions, as outlines a slot can be dropped on.
function EmptySlots({ count, onDrop }: { count: number; onDrop: () => void }) {
  return Array.from({ length: count }, (_, index) => (
    <li
      key={`empty-${index}`}
      className="slot slot-empty"
      onDragOver={(event) => event.preventDefault()}
      onDrop={(event) => {
        event.preventDefault();
        onDrop();
      }}
    >
      <span className="slot-outline" />
      <span className="slot-name">Empty</span>
    </li>
  ));
}

export function TeamHalf({ team, pokemonById, onMembers, onMoves, loadMoves, onRename, onDelete }: HalfProps) {
  const ids = team.pokemon_ids;
  const dragged = useRef<number | null>(null);
  const list = useRef<HTMLOListElement>(null);
  const [picking, setPicking] = useState<number | null>(null); // the slot whose moves are being chosen
  const edit = (change: <T>(list: T[]) => T[]) => editMembers(team, change);
  const focusIn = (index: number, selectors: string[]) => {
    const slot = list.current?.children[index];
    selectors.map((selector) => slot?.querySelector<HTMLElement>(selector)).find(Boolean)?.focus();
  };
  // A keyboard user keeps their place: after a move or a removal, focus goes
  // to the slot that now holds the moved Pokémon (or took the removed one's
  // place): the same control if it has one, else its other arrow, else its "×".
  function changeAndFocus(next: Members, index: number, control: string) {
    flushSync(() => onMembers(next));
    focusIn(Math.min(index, next.pokemon_ids.length - 1), [`.${control}`, ".slot-earlier, .slot-later", ".slot-control"]);
  }
  const move = (from: number, to: number, control: string) =>
    changeAndFocus(edit((list) => swapSlots(list, from, to)), to, control);
  function dropOn(target: number | "end") {
    const from = dragged.current;
    dragged.current = null;
    if (from === null || from === target) return;
    onMembers(edit((list) => (target === "end" ? moveToEnd(list, from) : swapSlots(list, from, target))));
  }
  // Closing the picker returns focus to the slot's "Moves".
  function closePicker(slot: number) {
    flushSync(() => setPicking(null));
    focusIn(slot, [".slot-moves"]);
  }
  return (
    <section className="half" aria-label={team.name}>
      <TeamHeader team={team} onRename={onRename} onDelete={onDelete} />
      <ol className="slots" ref={list}>
        {ids.map((id, index) => (
          <TeamSlot
            key={`${index}-${id}`}
            pokemon={pokemonById.get(id) ?? unknownPokemon(id)}
            ownMoves={team.moves[index] !== null}
            onRemove={() => changeAndFocus(edit((list) => removeSlot(list, index)), index, "slot-remove")}
            onMoves={() => setPicking(index)}
            onMoveEarlier={index > 0 ? () => move(index, index - 1, "slot-earlier") : undefined}
            onMoveLater={index < ids.length - 1 ? () => move(index, index + 1, "slot-later") : undefined}
            onDragStart={() => (dragged.current = index)}
            onDragEnd={() => (dragged.current = null)}
            onDrop={() => dropOn(index)}
          />
        ))}
        <EmptySlots count={TEAM_SIZE - ids.length} onDrop={() => dropOn("end")} />
      </ol>
      {picking !== null && (
        <MovePicker
          pokemon={pokemonById.get(ids[picking]!) ?? unknownPokemon(ids[picking]!)}
          chosen={team.moves[picking] ?? null}
          load={loadMoves}
          onSave={(moves) => void onMoves(picking, moves).then((saved) => saved && closePicker(picking))}
          onClose={() => closePicker(picking)}
        />
      )}
    </section>
  );
}
