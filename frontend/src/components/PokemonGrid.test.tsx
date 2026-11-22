// The grid with its controls, over the full 1,351-entry list from samples/.
import { act, fireEvent, render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import { CENSUS } from "../test/census";
import { scrollSentinelIntoView } from "../test/observer";
import { PokemonGrid } from "./PokemonGrid";

const CHECKBOX_LABEL = "Hide special versions (Mega, regional and others)";

function renderGrid(added = true) {
  const onAdd = vi.fn().mockResolvedValue(added);
  const { container } = render(<PokemonGrid pokemon={CENSUS} onAdd={onAdd} />);
  const cardNames = () => [...container.querySelectorAll(".card-name")].map((name) => name.textContent);
  return { container, onAdd, cardNames };
}

const searchBox = () => screen.getByRole("searchbox") as HTMLInputElement;
const typeFilter = () => screen.getByRole("combobox", { name: "Type" }) as HTMLSelectElement;
const checkbox = () => screen.getByRole("checkbox", { name: CHECKBOX_LABEL }) as HTMLInputElement;
const typeIn = (text: string) => fireEvent.change(searchBox(), { target: { value: text } });
const pressEnter = async () => act(async () => void fireEvent.keyDown(searchBox(), { key: "Enter" }));

test("opens with all 1,351 entries counted, the checkbox unticked and 60 cards drawn", () => {
  const { cardNames } = renderGrid();
  expect(screen.getByRole("status").textContent).toBe("Showing 1,351 of 1,351");
  expect(checkbox().checked).toBe(false);
  expect(cardNames()).toHaveLength(60);
  expect(cardNames().slice(0, 3)).toEqual(["Bulbasaur", "Ivysaur", "Venusaur"]);
});

test("60 more cards are drawn each time the end of the grid scrolls into view", () => {
  const { cardNames } = renderGrid();
  act(scrollSentinelIntoView);
  expect(cardNames()).toHaveLength(120);
  act(scrollSentinelIntoView);
  expect(cardNames()).toHaveLength(180);
});

test("ticking the checkbox leaves the 1,025 default entries", () => {
  renderGrid();
  fireEvent.click(checkbox());
  expect(screen.getByRole("status").textContent).toBe("Showing 1,025 of 1,351");
});

test("search results are drawn best match first", () => {
  const { cardNames } = renderGrid();
  typeIn("char");
  expect(screen.getByRole("status").textContent).toBe("Showing 10 of 1,351");
  expect(cardNames()).toEqual([
    "Charmander", "Charmeleon", "Charizard", "Charjabug", "Charcadet",
    "Charizard-mega-x", "Charizard-mega-y", "Charizard-gmax", "Chimchar", "Pecharunt",
  ]);
});

test("the type filter offers all types and the 18 standard ones", () => {
  renderGrid();
  expect(typeFilter().options).toHaveLength(19);
  fireEvent.change(typeFilter(), { target: { value: "ghost" } });
  expect(screen.getByRole("status").textContent).toBe("Showing 96 of 1,351");
});

test("changing a filter starts again from the first 60 cards", () => {
  const { cardNames } = renderGrid();
  act(scrollSentinelIntoView);
  expect(cardNames()).toHaveLength(120);
  fireEvent.click(checkbox());
  expect(cardNames()).toHaveLength(60);
});

test("no match shows a message, and 'Clear filters' restores all 1,351", () => {
  const { cardNames } = renderGrid();
  typeIn("pikachoo");
  fireEvent.change(typeFilter(), { target: { value: "fire" } });
  fireEvent.click(checkbox());
  expect(screen.getByText('No Pokémon match "pikachoo"')).toBeTruthy();
  expect(cardNames()).toEqual([]);

  fireEvent.click(screen.getByRole("button", { name: "Clear filters" }));
  expect(screen.getByRole("status").textContent).toBe("Showing 1,351 of 1,351");
  expect(searchBox().value).toBe("");
  expect(typeFilter().value).toBe("");
  expect(checkbox().checked).toBe(false);
});

test("Enter adds the top result and clears the box", async () => {
  const { onAdd } = renderGrid();
  typeIn("25");
  await pressEnter();
  expect(onAdd).toHaveBeenCalledExactlyOnceWith(expect.objectContaining({ name: "pikachu" }));
  expect(searchBox().value).toBe("");
});

test("Enter keeps the query when the Pokémon could not be added", async () => {
  const { onAdd } = renderGrid(false);
  typeIn("pika");
  await pressEnter();
  expect(onAdd).toHaveBeenCalledTimes(1);
  expect(searchBox().value).toBe("pika");
});

test("Enter in an empty or blank box adds nothing, even with a type filter set", async () => {
  const { onAdd } = renderGrid();
  fireEvent.change(typeFilter(), { target: { value: "fire" } });
  await pressEnter();
  typeIn("   ");
  await pressEnter();
  expect(onAdd).not.toHaveBeenCalled();
});

test("Enter with nothing matching adds nothing and keeps the query", async () => {
  const { onAdd } = renderGrid();
  typeIn("pikachoo");
  await pressEnter();
  expect(onAdd).not.toHaveBeenCalled();
  expect(searchBox().value).toBe("pikachoo");
});

test("the words 'alternate forms' appear nowhere", () => {
  const { container } = renderGrid();
  expect(container.textContent?.toLowerCase()).not.toContain("alternate form");
});
