// Contrast is computed here with the WCAG 2 formula
// (https://www.w3.org/TR/WCAG21/#dfn-contrast-ratio), independently of the
// product code, which only stores the colours.
import { expect, test } from "vitest";
import { ALERT_COLOURS, MATCHUP_COLOURS, TYPE_COLOURS, type MatchupLevel } from "./colours";
import { TYPE_NAMES } from "./types";

function channel(hex: string, start: number): number {
  const value = parseInt(hex.slice(start, start + 2), 16) / 255;
  return value <= 0.03928 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
}

function luminance(hex: string): number {
  return 0.2126 * channel(hex, 1) + 0.7152 * channel(hex, 3) + 0.0722 * channel(hex, 5);
}

function contrast(a: string, b: string): number {
  const [light, dark] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (light! + 0.05) / (dark! + 0.05);
}

test.each(TYPE_NAMES)("%s pill text has at least 4.5:1 contrast on its tint", (type) => {
  const { tint, text } = TYPE_COLOURS[type];
  expect(contrast(text, tint)).toBeGreaterThanOrEqual(4.5);
});

test.each(["text", "struck"] as const)("the alert panel's %s colour has at least 4.5:1 contrast on its fill", (key) => {
  expect(contrast(ALERT_COLOURS[key], ALERT_COLOURS.fill)).toBeGreaterThanOrEqual(4.5);
});

test("the formula reproduces known ratios", () => {
  expect(contrast("#000000", "#FFFFFF")).toBeCloseTo(21, 5);
  // The design table gives 5.43 for grass and 11.32 for dark, and 4.80 for the
  // alert panel's struck-through value on its fill.
  expect(contrast(TYPE_COLOURS.grass.text, TYPE_COLOURS.grass.tint)).toBeCloseTo(5.43, 2);
  expect(contrast(TYPE_COLOURS.dark.text, TYPE_COLOURS.dark.tint)).toBeCloseTo(11.32, 2);
  expect(contrast(ALERT_COLOURS.struck, ALERT_COLOURS.fill)).toBeCloseTo(4.8, 2);
});

test.each(Object.keys(MATCHUP_COLOURS) as MatchupLevel[])("the %s matchup label has at least 4.5:1 contrast", (level) => {
  const { fill, text } = MATCHUP_COLOURS[level];
  expect(contrast(text, fill)).toBeGreaterThanOrEqual(4.5);
});
