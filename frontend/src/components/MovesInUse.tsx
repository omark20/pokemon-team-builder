// The moves a team member is set to use: four positions, two by two. A filled
// position shows the move, its type and numbers, and a × that removes it; an
// empty one is a dashed outline. A chosen move that PokéAPI no longer lists for
// the Pokémon is struck through, with its ×.
import { typeStyle } from "../colours";
import { MOST_MOVES, classLine, inUse, type MoveOption, type Positions } from "../moveChoice";
import { displayName, moveName } from "../types";

interface InUseProps {
  pokemonName: string;
  positions: Positions;
  movesById: Map<number, MoveOption>;
  chosenNames: Map<number, string>; // names of chosen moves, for any no longer listed
  defaultInUse: boolean;
  onRemove: (id: number) => void;
  onUseDefault: () => void;
}

function Position({ id, props }: { id: number | null; props: InUseProps }) {
  if (id === null) return <li className="move-position move-empty">Empty</li>;
  const move = props.movesById.get(id);
  const name = moveName(move?.name ?? props.chosenNames.get(id) ?? String(id));
  return (
    <li className="move-position">
      {move ? (
        <>
          <strong>{name}</strong>{" "}
          <span className="pill" style={typeStyle(move.type)}>
            {displayName(move.type)}
          </span>
          <span className="move-numbers">{classLine(move)}</span>
        </>
      ) : (
        <>
          <s>{name}</s>
          <span className="move-numbers">no longer listed for {props.pokemonName}</span>
        </>
      )}
      <button type="button" className="move-remove" aria-label={`Remove ${name}`} onClick={() => props.onRemove(id)}>
        ×
      </button>
    </li>
  );
}

export function MovesInUse(props: InUseProps) {
  const count = inUse(props.positions).length;
  const status = props.defaultInUse ? `These are ${props.pokemonName}'s default moves.` : "You chose these moves.";
  return (
    <section className="moves-in-use" aria-labelledby="moves-in-use-title">
      <h3 id="moves-in-use-title">
        Moves in use ({count} of {MOST_MOVES})
      </h3>
      <p className="moves-status">{status}</p>
      <ul className="move-positions">
        {props.positions.map((id, index) => (
          <Position key={index} id={id} props={props} />
        ))}
      </ul>
      <button type="button" className="link-button use-default" disabled={props.defaultInUse} onClick={props.onUseDefault}>
        Use the default moves
      </button>
    </section>
  );
}
