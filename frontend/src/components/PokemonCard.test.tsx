// Expected values come from the captured PokéAPI responses in samples/.
import { fireEvent, render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import charizardSample from "../../../samples/pokemon_6_charizard_dual_type.json";
import { byName } from "../test/census";
import type { Pokemon } from "../types";
import { PokemonCard } from "./PokemonCard";

const LABELS = ["HP", "Atk", "Def", "SpA", "SpD", "Spe"];

function renderCard(pokemon: Pokemon, onAdd = vi.fn()) {
  const { container } = render(<PokemonCard pokemon={pokemon} onAdd={onAdd} />);
  return { container, onAdd };
}

const barWidths = (container: HTMLElement) =>
  [...container.querySelectorAll<HTMLElement>(".stat-fill")].map((bar) => bar.style.width);

test("Charizard's card shows its name, both types and the six captured base stats", () => {
  const { container } = renderCard(byName("charizard"));
  expect(screen.getByRole("heading", { name: "Charizard" })).toBeTruthy();
  const pills = [...container.querySelectorAll(".pill")].map((pill) => pill.textContent);
  expect(pills).toEqual(charizardSample.types.map((entry) => entry.type.name));
  expect(pills).toEqual(["fire", "flying"]);

  const rows = [...container.querySelectorAll(".stat")];
  expect(rows).toHaveLength(6);
  rows.forEach((row, index) => {
    expect(row.querySelector(".stat-label")?.textContent).toBe(LABELS[index]);
    expect(row.querySelector(".stat-value")?.textContent).toBe(
      String(charizardSample.stats[index]?.base_stat),
    );
    expect(row.querySelector(".stat-fill")).toBeTruthy();
  });
});

test("a single-type Pokémon shows one pill", () => {
  const { container } = renderCard(byName("pikachu"));
  const pills = [...container.querySelectorAll(".pill")].map((pill) => pill.textContent);
  expect(pills).toEqual(["electric"]);
});

test("the picture loads lazily, at a fixed size, from the stored sprite address", () => {
  renderCard(byName("charizard"));
  const image = screen.getByAltText("Charizard") as HTMLImageElement;
  expect(image.getAttribute("src")).toBe(charizardSample.sprites.front_default);
  expect(image.getAttribute("loading")).toBe("lazy");
  expect(image.getAttribute("width")).toBe("64");
  expect(image.getAttribute("height")).toBe("64");
});

test("an entry with no sprite shows a placeholder and no image", () => {
  // samples/pokemon_10264_null_sprite.json: sprites.front_default is null.
  const { container } = renderCard(byName("koraidon-limited-build"));
  expect(container.querySelector("img")).toBeNull();
  expect(screen.getByRole("img", { name: "No picture of Koraidon-limited-build" })).toBeTruthy();
});

test("an image that fails to load is replaced by the placeholder", () => {
  const { container } = renderCard(byName("charizard"));
  fireEvent.error(screen.getByAltText("Charizard"));
  expect(container.querySelector("img")).toBeNull();
  expect(screen.getByRole("img", { name: "No picture of Charizard" })).toBeTruthy();
});

test("a stat of 80 draws half a bar and a stat of 255 a full bar with its true number", () => {
  const pokemon = { ...byName("pikachu"), stats: [80, 255, 160, 0, 40, 200] };
  const { container } = renderCard(pokemon);
  expect(barWidths(container)).toEqual(["50%", "100%", "100%", "0%", "25%", "100%"]);
  expect(container.querySelectorAll(".stat-value")[1]?.textContent).toBe("255");
});

test("the card carries no Pokédex number and no stat total", () => {
  // Charizard is number 6 and its stats total 534; no stat contains a 6.
  const { container } = renderCard(byName("charizard"));
  expect(container.textContent).not.toMatch(/6|534/);
});

test("the stat bars and the sprite circle take the first type's colours", () => {
  const { container } = renderCard(byName("charizard"));
  const card = container.querySelector<HTMLElement>(".card");
  expect(card?.style.getPropertyValue("--type-tint")).toBe("#FAECE7"); // fire
  expect(card?.style.getPropertyValue("--type-bar")).toBe("#D85A30");
  const flying = container.querySelectorAll<HTMLElement>(".pill")[1];
  expect(flying?.style.getPropertyValue("--type-text")).toBe("#0F6E56");
});

test("'Add to team' hands the Pokémon to the caller", () => {
  const charizard = byName("charizard");
  const { onAdd } = renderCard(charizard);
  fireEvent.click(screen.getByRole("button", { name: "Add to team" }));
  expect(onAdd).toHaveBeenCalledExactlyOnceWith(charizard);
});
