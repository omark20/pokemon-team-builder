// One filled position of a team: picture and name, dragged onto another slot
// to swap them. A "×" removes the slot and two arrows move it one place; they
// stay in the page for the keyboard but are hidden, and ignore pointer clicks,
// until the slot is "revealed" by a hovering mouse, keyboard focus or a tap.
// So a first tap on a phone only shows them, and the next one acts.
import { useRef, useState, type DragEvent, type MouseEvent, type ReactNode } from "react";
import { typeStyle } from "../colours";
import { displayName, type Pokemon } from "../types";
import { Sprite } from "./Sprite";

export interface SlotActions {
  onRemove: () => void;
  onMoveEarlier?: () => void; // absent for the first slot
  onMoveLater?: () => void; // absent for the last slot
  onDragStart: () => void;
  onDragEnd: () => void; // the drag finished, dropped or cancelled
  onDrop: () => void;
}

interface SlotProps extends SlotActions {
  pokemon: Pokemon;
}

// Whether the controls are showing, and whether they were showing when the
// current pointer press began: a press that revealed them must not also act.
function useReveal() {
  const [hovered, setHovered] = useState(false);
  const [focused, setFocused] = useState(false);
  const [tapped, setTapped] = useState(false);
  const revealed = hovered || focused || tapped;
  const revealedAtPress = useRef(false);
  const handlers = {
    onPointerEnter: (event: { pointerType: string }) => setHovered(event.pointerType === "mouse"),
    onPointerLeave: () => setHovered(false),
    onPointerDownCapture: (event: { pointerType: string }) => {
      revealedAtPress.current = revealed;
      if (event.pointerType !== "mouse") setTapped(true);
    },
    onFocus: () => setFocused(true),
    onBlur: (event: { currentTarget: Element; relatedTarget: Element | null }) => {
      if (event.currentTarget.contains(event.relatedTarget)) return;
      setFocused(false);
      setTapped(false);
    },
  };
  // A pointer click has detail 1 or more; Enter or Space on a button gives 0.
  const acts = (event: MouseEvent) => event.detail === 0 || revealedAtPress.current;
  return { revealed, handlers, acts };
}

function SlotControl(props: { label: string; className: string; children: ReactNode; act: () => void; acts: (e: MouseEvent) => boolean }) {
  return (
    <button
      type="button"
      className={`slot-control ${props.className}`}
      aria-label={props.label}
      onClick={(event) => props.acts(event) && props.act()}
    >
      {props.children}
    </button>
  );
}

export function TeamSlot({ pokemon, onRemove, onMoveEarlier, onMoveLater, onDragStart, onDragEnd, onDrop }: SlotProps) {
  const { revealed, handlers, acts } = useReveal();
  const [dropTarget, setDropTarget] = useState(false);
  const name = displayName(pokemon.name);
  function handleDrop(event: DragEvent) {
    event.preventDefault();
    setDropTarget(false);
    onDrop();
  }
  return (
    <li
      className={`slot slot-filled${revealed ? " revealed" : ""}${dropTarget ? " drop-target" : ""}`}
      style={typeStyle(pokemon.types[0]!)}
      tabIndex={-1}
      draggable
      onDragStart={(event) => {
        event.dataTransfer.effectAllowed = "move";
        event.dataTransfer.setData("text/plain", name); // Firefox starts a drag only with data
        onDragStart();
      }}
      onDragOver={(event) => {
        event.preventDefault();
        setDropTarget(true);
      }}
      onDragLeave={() => setDropTarget(false)}
      onDragEnd={onDragEnd}
      onDrop={handleDrop}
      {...handlers}
    >
      <Sprite url={pokemon.sprite_url} name={name} size={48} />
      <span className="slot-name">{name}</span>
      <SlotControl label={`Remove ${name}`} className="slot-remove" act={onRemove} acts={acts}>
        ×
      </SlotControl>
      {onMoveEarlier && (
        <SlotControl label={`Move ${name} earlier`} className="slot-earlier" act={onMoveEarlier} acts={acts}>
          ‹
        </SlotControl>
      )}
      {onMoveLater && (
        <SlotControl label={`Move ${name} later`} className="slot-later" act={onMoveLater} acts={acts}>
          ›
        </SlotControl>
      )}
    </li>
  );
}
