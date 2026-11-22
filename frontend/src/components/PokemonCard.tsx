// One Pokémon in the grid: its picture in a circle tinted with its first
// type's colour, its name, a pill per type, its six base stats as bars, and a
// button that adds it to the team being edited.
import { useState } from "react";
import { typeStyle } from "../colours";
import { displayName, STAT_LABELS, type Pokemon } from "../types";

// A stat this high or higher draws a full bar; the number beside it is always
// the true value.
const FULL_BAR = 160;

interface CardProps {
  pokemon: Pokemon;
  onAdd: (pokemon: Pokemon) => void;
}

// The picture, or a placeholder when PokéAPI has none or the image fails.
function Sprite({ url, name }: { url: string | null; name: string }) {
  const [failed, setFailed] = useState(false);
  if (url === null || failed) {
    return (
      <div className="sprite sprite-missing" role="img" aria-label={`No picture of ${name}`}>
        ?
      </div>
    );
  }
  return (
    <div className="sprite">
      <img src={url} alt={name} width={64} height={64} loading="lazy" onError={() => setFailed(true)} />
    </div>
  );
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

export function PokemonCard({ pokemon, onAdd }: CardProps) {
  const name = displayName(pokemon.name);
  return (
    <article className="card" style={typeStyle(pokemon.types[0]!)}>
      <Sprite url={pokemon.sprite_url} name={name} />
      <h3 className="card-name">{name}</h3>
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
      <button type="button" className="card-add" onClick={() => onAdd(pokemon)}>
        Add to team
      </button>
    </article>
  );
}
