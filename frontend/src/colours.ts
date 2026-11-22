// The colour of each Pokémon type, defined once. Each type has a pale tint (the
// sprite's circle and the type pill's background), a dark text shade (the
// pill's text, which must keep a 4.5 to 1 contrast on the tint) and a mid tone
// (the stat bars). Components read them through CSS custom properties.
import type { CSSProperties } from "react";
import type { TypeName } from "./types";

interface TypeColour {
  tint: string;
  text: string;
  bar: string;
}

export const TYPE_COLOURS: Record<TypeName, TypeColour> = {
  normal: { tint: "#F1EFE8", text: "#5F5E5A", bar: "#888780" },
  fire: { tint: "#FAECE7", text: "#993C1D", bar: "#D85A30" },
  water: { tint: "#E6F1FB", text: "#185FA5", bar: "#378ADD" },
  grass: { tint: "#EAF3DE", text: "#3B6D11", bar: "#639922" },
  electric: { tint: "#FAEEDA", text: "#854F0B", bar: "#EF9F27" },
  ice: { tint: "#E6F1FB", text: "#0C447C", bar: "#85B7EB" },
  fighting: { tint: "#FAECE7", text: "#712B13", bar: "#B5482A" },
  poison: { tint: "#EEEDFE", text: "#534AB7", bar: "#7F77DD" },
  ground: { tint: "#FAEEDA", text: "#633806", bar: "#BA7517" },
  flying: { tint: "#E1F5EE", text: "#0F6E56", bar: "#1D9E75" },
  psychic: { tint: "#FBEAF0", text: "#72243E", bar: "#D4537E" },
  bug: { tint: "#EAF3DE", text: "#3B6D11", bar: "#8FA83A" },
  rock: { tint: "#F1EFE8", text: "#5F5E5A", bar: "#888780" },
  ghost: { tint: "#EEEDFE", text: "#3C3489", bar: "#7F77DD" },
  dragon: { tint: "#FBEAF0", text: "#993556", bar: "#D4537E" },
  dark: { tint: "#E9E7E1", text: "#2C2C2A", bar: "#5F5E5A" },
  steel: { tint: "#F1EFE8", text: "#444441", bar: "#9A9A95" },
  fairy: { tint: "#FBEAF0", text: "#993556", bar: "#ED93B1" },
};

// The custom properties --type-tint, --type-text and --type-bar for one type,
// set as a React style so the stylesheet can use them.
export function typeStyle(type: TypeName): CSSProperties {
  const colour = TYPE_COLOURS[type];
  return {
    "--type-tint": colour.tint,
    "--type-text": colour.text,
    "--type-bar": colour.bar,
  } as CSSProperties;
}
