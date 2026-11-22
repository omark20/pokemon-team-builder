// One Pokémon in the grid: its picture in a circle tinted with its first
// type's colour, its name, a pill per type, its six base stats as bars, and a
// button that adds it to the team being edited.
import { typeStyle } from "../colours";
import { TEAM_SIZE } from "../teamMoves";
import { displayName, STAT_LABELS, type Pokemon } from "../types";
import { Sprite } from "./Sprite";

// A stat this high or higher draws a full bar; the number beside it is always
// the true value.
const FULL_BAR = 160;

interface CardProps {
  pokemon: Pokemon;
  onAdd: (pokemon: Pokemon) => void;
  teamFull: boolean; // the team being edited has six; the button says so and waits
}

function StatBar({ index, value }: { index: number; value: number }) {
  const label = STAT_LABELS[index]!;
  const width = `${(Math.min(value, FULL_BAR) / FULL_BAR) * 100}%`;
  return (
    <div className="stat">
      <abbr className="stat-label" title={label.full}>
        {label.short}
      </abbr>
      <span className="stat-track">
        <span className="stat-fill" style={{ width }} />
      </span>
      <span className="stat-value">{value}</span>
    </div>
  );
}

export function PokemonCard({ pokemon, onAdd, teamFull }: CardProps) {
  const name = displayName(pokemon.name);
  return (
    <article className="card" style={typeStyle(pokemon.types[0]!)}>
      <Sprite url={pokemon.sprite_url} name={name} size={64} />
      <h3 className="card-name" tabIndex={-1}>
        {name}
      </h3>
      <div className="pills">
        {pokemon.types.map((type) => (
          <span key={type} className="pill" style={typeStyle(type)}>
            {type}
          </span>
        ))}
      </div>
      <div className="stats">
        {pokemon.stats.map((value, index) => (
          <StatBar key={index} index={index} value={value} />
        ))}
      </div>
      <button type="button" className="card-add" disabled={teamFull} onClick={() => onAdd(pokemon)}>
        {teamFull ? `Team full (${TEAM_SIZE}/${TEAM_SIZE})` : "Add to team"}
      </button>
    </article>
  );
}
