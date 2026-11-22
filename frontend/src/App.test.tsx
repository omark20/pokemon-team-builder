// The page's loading, loaded and failed states, with the network replaced.
import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import App from "./App";
import { CENSUS } from "./test/census";

const listResponse = () => new Response(JSON.stringify(CENSUS), { status: 200 });

function stubFetch(...responses: (Response | Error)[]) {
  const fetchMock = vi.fn();
  for (const response of responses) {
    if (response instanceof Error) fetchMock.mockRejectedValueOnce(response);
    else fetchMock.mockResolvedValueOnce(response);
  }
  vi.spyOn(globalThis, "fetch").mockImplementation(fetchMock);
  return fetchMock;
}

afterEach(() => vi.restoreAllMocks());

test("shows placeholder cards, then the grid loaded from the app's own API", async () => {
  const fetchMock = stubFetch(listResponse());
  render(<App />);
  expect(screen.getByLabelText("Loading Pokémon")).toBeTruthy();
  expect((await screen.findByRole("status")).textContent).toBe("Showing 1,351 of 1,351");
  expect(fetchMock).toHaveBeenCalledExactlyOnceWith("/api/pokemon");
});

test("a failed load shows an error, and 'Try again' loads the list", async () => {
  stubFetch(new Response("{}", { status: 500 }), listResponse());
  render(<App />);
  expect(await screen.findByText("Couldn't load Pokémon")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Try again" }));
  expect((await screen.findByRole("status")).textContent).toBe("Showing 1,351 of 1,351");
});

test("a network failure shows the same error", async () => {
  stubFetch(new TypeError("offline"));
  render(<App />);
  expect(await screen.findByRole("alert")).toBeTruthy();
});
