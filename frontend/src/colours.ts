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

// The change-alert panel ("marigold"): its fill, border and text, and the
// colour of a struck-through old value. Both text colours keep a 4.5 to 1
// contrast on the fill; nothing inside the panel is white.
export const ALERT_COLOURS = {
  fill: "#FFE2A8",
  border: "#EBC06A",
  text: "#5E4300",
  struck: "#77601F",
};

// The matchup scale in the details panel, greener the stronger: deep green,
// light green, neutral, light red, deep red. The two deep ends are solid fills
// with white text, and the light steps are cooler than the grass and fire type
// pills, so a green label does not read as a grass type. Every text colour
// keeps a 4.5 to 1 contrast on its fill.
export type MatchupLevel = "strong" | "good" | "even" | "weak" | "bad";

export const MATCHUP_COLOURS: Record<MatchupLevel, { fill: string; text: string }> = {
  strong: { fill: "#1E6B3A", text: "#FFFFFF" },
  good: { fill: "#CDEBD5", text: "#14532D" },
  even: { fill: "#ECECEA", text: "#46463F" },
  weak: { fill: "#F9D5D5", text: "#7F1D1D" },
  bad: { fill: "#A11D1D", text: "#FFFFFF" },
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

// The alert panel's colours as the custom properties --alert-fill and so on.
export function alertStyle(): CSSProperties {
  return {
    "--alert-fill": ALERT_COLOURS.fill,
    "--alert-border": ALERT_COLOURS.border,
    "--alert-text": ALERT_COLOURS.text,
    "--alert-struck": ALERT_COLOURS.struck,
  } as CSSProperties;
}
