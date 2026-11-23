// The page-wide error boundary: a part of the page that throws while drawing is
// replaced by a message and a way to reload, instead of a blank page.
import { render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import { ErrorBoundary, PAGE_FAILED } from "./ErrorBoundary";

function Broken(): never {
  throw new Error("an answer in a shape the page did not expect");
}

test("a part that throws while drawing is replaced by the message and a reload button, and the error is logged", () => {
  const logged = vi.spyOn(console, "error").mockImplementation(() => {});
  render(
    <ErrorBoundary>
      <Broken />
    </ErrorBoundary>,
  );
  expect(screen.getByRole("alert").textContent).toContain(PAGE_FAILED);
  expect(screen.getByRole("button", { name: "Reload the page" })).toBeTruthy();
  expect(logged.mock.calls.some((call) => call[0] === "The page failed to render:")).toBe(true);
  logged.mockRestore();
});

test("a part that draws without error is shown as it is", () => {
  render(
    <ErrorBoundary>
      <p>Team 1</p>
    </ErrorBoundary>,
  );
  expect(screen.getByText("Team 1")).toBeTruthy();
  expect(screen.queryByRole("alert")).toBeNull();
});
