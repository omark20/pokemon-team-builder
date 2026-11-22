import { fireEvent, render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import { Sprite } from "./Sprite";

const FIRST = "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/6.png";
const SECOND = "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/9.png";

test("after a picture fails, a different picture in the same place still loads", () => {
  const { rerender } = render(<Sprite url={FIRST} name="Charizard" size={48} />);
  fireEvent.error(screen.getByRole("img"));
  expect(screen.getByRole("img", { name: "No picture of Charizard" })).toBeTruthy();
  rerender(<Sprite url={SECOND} name="Blastoise" size={48} />);
  expect(screen.getByRole("img").getAttribute("src")).toBe(SECOND);
});
