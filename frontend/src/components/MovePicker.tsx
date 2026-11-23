// The dialog for choosing a team member's moves: the moves in use, a way to find
// a move, the list, and "Save" and "Cancel" fixed at the bottom. Saving the
// default four, in any order, stores "not chosen" (null). The dialog never closes
// itself: the caller closes it after a save succeeds, and keeps it open if the
// save fails.
import { useCallback, useEffect, useState } from "react";
import { typeStyle } from "../colours";
import {
  MOST_MOVES,
  inUse,
  positionsOf,
  sameMoves,
  withMove,
  withoutMove,
  type MoveChoices,
} from "../moveChoice";
import { displayName, type ChosenMove, type Pokemon, type SlotMoves } from "../types";
import { DialogFrame } from "./DialogFrame";
import { MoveList } from "./MoveList";
import { MovesInUse } from "./MovesInUse";
import { Sprite } from "./Sprite";

interface PickerProps {
  pokemon: Pokemon;
  chosen: SlotMoves; // null: the slot uses the Pokémon's default four
  load: (pokemonId: number) => Promise<MoveChoices>;
  onSave: (chosen: SlotMoves) => void;
  onClose: () => void;
}

type Loaded = { status: "loading" } | { status: "failed" } | { status: "ready"; choices: MoveChoices };

function Buttons({ onSave, onClose }: { onSave?: () => void; onClose: () => void }) {
  return (
    <div className="move-buttons">
      <button type="button" className="primary" disabled={!onSave} onClick={onSave}>
        Save
      </button>
      <button type="button" onClick={onClose}>
        Cancel
      </button>
    </div>
  );
}

function MoveEditor({ pokemon, chosen, choices, onSave, onClose }: Omit<PickerProps, "load"> & { choices: MoveChoices }) {
  const start = chosen?.map((move) => move.id) ?? choices.default;
  const [positions, setPositions] = useState(() => positionsOf(start));
  const used = inUse(positions);
  const defaultInUse = sameMoves(used, choices.default);
  const canSave = used.length > 0 && !sameMoves(used, start);
  const toggle = (id: number) => setPositions(used.includes(id) ? withoutMove(positions, id) : withMove(positions, id));
  const names = new Map([...(chosen ?? []), ...choices.moves].map((move) => [move.id, move.name]));
  const save = () => onSave(defaultInUse ? null : used.map((id): ChosenMove => ({ id, name: names.get(id)! })));
  return (
    <>
      <MovesInUse
        pokemonName={displayName(pokemon.name)}
        positions={positions}
        movesById={new Map(choices.moves.map((move) => [move.id, move]))}
        chosenNames={new Map(chosen?.map((move) => [move.id, move.name]))}
        defaultInUse={defaultInUse}
        onRemove={(id) => setPositions(withoutMove(positions, id))}
        onUseDefault={() => setPositions(positionsOf(choices.default))}
      />
      <MoveList moves={choices.moves} used={used} full={used.length === MOST_MOVES} onToggle={toggle} />
      {used.length === 0 && <p className="move-full">Choose at least one move, or use the default moves.</p>}
      <Buttons onSave={canSave ? save : undefined} onClose={onClose} />
    </>
  );
}

// The body for each state of the load: waiting, failed, nothing to choose from, or the editor.
function PickerBody({ loaded, retry, ...props }: Omit<PickerProps, "load"> & { loaded: Loaded; retry: () => void }) {
  if (loaded.status === "loading") {
    return (
      <>
        <p>Loading moves…</p>
        <Buttons onClose={props.onClose} />
      </>
    );
  }
  if (loaded.status === "failed") {
    return (
      <>
        <p role="alert">
          The moves could not be loaded.{" "}
          <button type="button" onClick={retry}>
            Try again
          </button>
        </p>
        <Buttons onClose={props.onClose} />
      </>
    );
  }
  const { choices } = loaded;
  if (!choices.moves_listed || choices.moves.length === 0) {
    const none = choices.moves_listed ? "None of the moves PokéAPI lists for this Pokémon has a power of its own, so none can be chosen here." : "PokéAPI lists no moves for this Pokémon.";
    return (
      <>
        <p>{none}</p>
        <div className="move-buttons">
          <button type="button" onClick={props.onClose}>
            Close
          </button>
        </div>
      </>
    );
  }
  return <MoveEditor {...props} choices={choices} />;
}

export function MovePicker({ load, ...props }: PickerProps) {
  const [loaded, setLoaded] = useState<Loaded>({ status: "loading" });
  const pokemonId = props.pokemon.id;
  const fetchMoves = useCallback(() => {
    load(pokemonId).then(
      (choices) => setLoaded({ status: "ready", choices }),
      () => setLoaded({ status: "failed" }),
    );
  }, [load, pokemonId]);
  useEffect(fetchMoves, [fetchMoves]);
  const retry = () => {
    setLoaded({ status: "loading" });
    fetchMoves();
  };
  const name = displayName(props.pokemon.name);
  return (
    <DialogFrame title={`${name}'s moves`} onClose={props.onClose}>
      <div className="move-identity">
        <Sprite url={props.pokemon.sprite_url} name={name} size={48} />
        {props.pokemon.types.map((type) => (
          <span key={type} className="pill" style={typeStyle(type)}>
            {displayName(type)}
          </span>
        ))}
      </div>
      <div className="move-picker">
        <PickerBody {...props} loaded={loaded} retry={retry} />
      </div>
    </DialogFrame>
  );
}
