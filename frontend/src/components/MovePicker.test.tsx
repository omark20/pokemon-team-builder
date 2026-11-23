// The move picker on its own, for Charizard. test/charizardMoves.json is what the
// backend's counter core gives from the captures in samples/: Charizard's 78 moves
// that count, and its default four (Overheat, Earthquake, Hurricane, Outrage).
import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import type { MoveChoices } from "../moveChoice";
import type { ChosenMove } from "../types";
import { CENSUS } from "../test/census";
import moves from "../test/charizardMoves.json";
import { MovePicker } from "./MovePicker";

const CHARIZARD = CENSUS.find((pokemon) => pokemon.name === "charizard")!;
const CHOICES = moves as MoveChoices;

async function open(chosen: ChosenMove[] | null = null, load = () => Promise.resolve(CHOICES)) {
  const onSave = vi.fn();
  const onClose = vi.fn();
  render(<MovePicker pokemon={CHARIZARD} chosen={chosen} load={load} onSave={onSave} onClose={onClose} />);
  await screen.findByRole("searchbox", { name: "Search moves" });
  return { onSave, onClose };
}

const positions = () => [...document.querySelectorAll(".move-position")].map((position) => position.textContent);
const rows = () => [...document.querySelectorAll(".move-row")].map((row) => row.textContent);
const row = (name: string) => screen.getByRole("button", { name: new RegExp(`^${name}, `) });
const save = () => screen.getByRole("button", { name: "Save" }) as HTMLButtonElement;
const useDefault = () => screen.getByRole("button", { name: "Use the default moves" }) as HTMLButtonElement;

test("it opens on the default four with the search box focused, and nothing to save", async () => {
  await open();
  expect(screen.getByRole("dialog", { name: "Charizard's moves" })).toBeTruthy();
  expect(document.activeElement).toBe(screen.getByRole("searchbox"));
  expect(screen.getByRole("heading", { name: "Moves in use (4 of 4)" })).toBeTruthy();
  expect(screen.getByText("These are Charizard's default moves.")).toBeTruthy();
  expect(positions()).toEqual([
    "Overheat FireSpecial · power 130 · 90% accurate×",
    "Earthquake GroundPhysical · power 100 · 100% accurate×",
    "Hurricane FlyingSpecial · power 110 · 70% accurate×",
    "Outrage DragonPhysical · power 120 · 100% accurate×",
  ]);
  expect([useDefault().disabled, save().disabled]).toEqual([true, true]);
});

test("the list is strongest first, then by name, and a move that cannot miss says so", async () => {
  await open();
  expect(rows()).toHaveLength(78);
  expect(rows().slice(0, 4)).toEqual([
    "✓ Overheat in useFireSpecial13090%",
    "Double EdgeNormalPhysical120100%",
    "Flare BlitzFirePhysical120100%",
    "Focus BlastFightingSpecial12070%",
  ]);
  expect(rows()).toContain("SwiftNormalSpecial60never misses");
  expect(row("Overheat").getAttribute("aria-label")).toBe("Overheat, Fire, Special · power 130 · 90% accurate, in use");
});

test("the search box and the type drop-down narrow the list, and say when nothing matches", async () => {
  await open();
  const types = within(screen.getByRole("combobox", { name: "Move type" })).getAllByRole("option");
  expect(types).toHaveLength(13); // "All types" and the 12 types Charizard has moves of
  fireEvent.change(screen.getByRole("combobox", { name: "Move type" }), { target: { value: "fighting" } });
  fireEvent.change(screen.getByRole("searchbox"), { target: { value: "blast" } });
  expect(rows()).toEqual(["Focus BlastFightingSpecial12070%"]);
  fireEvent.change(screen.getByRole("searchbox"), { target: { value: "zzz" } });
  expect(screen.getByText("No move matches.")).toBeTruthy();
});

test("with four in use the other rows do nothing; removing one frees a position the next row fills", async () => {
  const { onSave } = await open();
  expect(screen.getByText("Four moves in use. Remove one to add another.")).toBeTruthy();
  expect((row("Focus Blast") as HTMLButtonElement).disabled).toBe(true);
  fireEvent.click(screen.getByRole("button", { name: "Remove Earthquake" }));
  expect(screen.getByRole("heading", { name: "Moves in use (3 of 4)" })).toBeTruthy();
  expect(positions()[1]).toBe("Empty");
  fireEvent.click(row("Focus Blast"));
  expect(positions()[1]).toBe("Focus Blast FightingSpecial · power 120 · 70% accurate×");
  expect(screen.getByText("You chose these moves.")).toBeTruthy();
  fireEvent.click(save());
  expect(onSave).toHaveBeenCalledWith([
    { id: 315, name: "overheat" },
    { id: 411, name: "focus-blast" },
    { id: 542, name: "hurricane" },
    { id: 200, name: "outrage" },
  ]);
});

test("pressing a move in use removes it, and with none left Save waits for a move", async () => {
  await open();
  for (const name of ["Overheat", "Earthquake", "Hurricane", "Outrage"]) fireEvent.click(row(name));
  expect(positions()).toEqual(["Empty", "Empty", "Empty", "Empty"]);
  expect(save().disabled).toBe(true);
  expect(screen.getByText("Choose at least one move, or use the default moves.")).toBeTruthy();
});

test("using the default moves after a choice and saving stores 'not chosen'", async () => {
  const { onSave } = await open([{ id: 411, name: "focus-blast" }]);
  expect(screen.getByText("You chose these moves.")).toBeTruthy();
  fireEvent.click(useDefault());
  expect(positions().map((text) => text?.split(" ")[0])).toEqual(["Overheat", "Earthquake", "Hurricane", "Outrage"]);
  fireEvent.click(save());
  expect(onSave).toHaveBeenCalledWith(null);
});

test("a chosen move no longer listed is struck through and can be removed", async () => {
  await open([{ id: 89, name: "earthquake" }, { id: 99_999, name: "old-move" }]);
  const gone = document.querySelectorAll(".move-position")[1]!;
  expect([gone.querySelector("s")?.textContent, gone.textContent]).toEqual(["Old Move", "Old Moveno longer listed for Charizard×"]);
  fireEvent.click(screen.getByRole("button", { name: "Remove Old Move" }));
  expect(positions()[1]).toBe("Empty");
});

test("a failed load says so and can be tried again, with Save disabled meanwhile", async () => {
  const load = vi.fn().mockRejectedValueOnce(new Error("down")).mockResolvedValueOnce(CHOICES);
  render(<MovePicker pokemon={CHARIZARD} chosen={null} load={load} onSave={vi.fn()} onClose={vi.fn()} />);
  expect(screen.getByText("Loading moves…")).toBeTruthy();
  expect(await screen.findByText(/The moves could not be loaded\./)).toBeTruthy();
  expect(save().disabled).toBe(true);
  await act(async () => fireEvent.click(screen.getByRole("button", { name: "Try again" })));
  expect(await screen.findByRole("searchbox")).toBeTruthy();
  expect(load).toHaveBeenCalledTimes(2);
});

test.each([
  { listed: false, says: "PokéAPI lists no moves for this Pokémon." },
  { listed: true, says: "None of the moves PokéAPI lists for this Pokémon has a power of its own, so none can be chosen here." },
])("with nothing to choose from (moves listed: $listed) it says why and has only Close", async ({ listed, says }) => {
  const onClose = vi.fn();
  const none = () => Promise.resolve({ moves: [], default: [], moves_listed: listed });
  render(<MovePicker pokemon={CHARIZARD} chosen={null} load={none} onSave={vi.fn()} onClose={onClose} />);
  expect(await screen.findByText(says)).toBeTruthy();
  expect(within(screen.getByRole("dialog")).getAllByRole("button").map((button) => button.textContent)).toEqual(["Close"]);
  fireEvent.click(screen.getByRole("button", { name: "Close" }));
  expect(onClose).toHaveBeenCalled();
});

test("Escape and Cancel close the dialog without saving", async () => {
  const { onSave, onClose } = await open();
  fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });
  fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
  expect([onClose.mock.calls.length, onSave.mock.calls.length]).toEqual([2, 0]);
});

test("Tab reaches each move's × before 'Use the default moves', then search and the type", async () => {
  await open([{ id: 89, name: "earthquake" }]);
  const order = [...screen.getByRole("dialog").querySelectorAll<HTMLElement>("button:not(:disabled), input, select")]
    .slice(0, 4)
    .map((control) => control.getAttribute("aria-label") ?? control.textContent);
  expect(order).toEqual(["Remove Earthquake", "Use the default moves", "Search moves", "Move type"]);
});
