// A Pokémon's picture in a circle tinted with its type colour (set by the
// parent), or a placeholder when PokéAPI has no picture or it fails to load.
import { useState } from "react";

interface SpriteProps {
  url: string | null;
  name: string;
  size: number; // the picture's width and height in pixels
}

export function Sprite({ url, name, size }: SpriteProps) {
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
      <img src={url} alt={name} width={size} height={size} loading="lazy" onError={() => setFailed(true)} />
    </div>
  );
}
