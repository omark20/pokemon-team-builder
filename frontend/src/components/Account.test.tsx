// The account links, the notice and the dialog, through the whole page against
// a stand-in backend.
import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { expect, test } from "vitest";
import App from "../App";
import { FakeServer } from "../test/fakeServer";
import type { Team } from "../types";

const TEAM: Team = { id: 1, name: "Team 1", pokemon_ids: [6] };
const NOTICE = "Your teams are saved in this browser only.";

async function start(teams: Team[] = [], username: string | null = null) {
  const server = new FakeServer(teams);
  server.username = username;
  render(<App />);
  await screen.findByText(/^Showing /);
  await act(async () => {}); // the session answer
  return server;
}

const topRight = () => document.querySelector<HTMLElement>(".account-links");
const notice = () => screen.queryByRole("region", { name: "Where your teams are saved" });
const dialog = () => within(screen.getByRole("dialog"));
const openDialog = (name: "Create account" | "Sign in") =>
  fireEvent.click(within(topRight() ?? notice()!).getByRole("button", { name }));

function fillIn(username: string, password: string) {
  fireEvent.change(dialog().getByLabelText("Username"), { target: { value: username } });
  fireEvent.change(dialog().getByLabelText("Password"), { target: { value: password } });
}

async function fillAndSubmit(username: string, password: string) {
  fillIn(username, password);
  await act(async () => fireEvent.submit(dialog().getByLabelText("Username").closest("form")!));
}

test("with no team: the two actions at the top right and no notice", async () => {
  await start();
  expect(within(topRight()!).getAllByRole("button").map((b) => b.textContent)).toEqual(["Create account", "Sign in"]);
  expect(notice()).toBeNull();
});

test("with a team: the notice with its exact text and actions, and nothing at the top right", async () => {
  await start([TEAM]);
  expect(within(notice()!).getByText(NOTICE)).toBeTruthy();
  const labels = within(notice()!).getAllByRole("button").map((b) => b.getAttribute("aria-label") ?? b.textContent);
  expect(labels).toEqual(["Create account", "Sign in", "Close this notice"]);
  expect(topRight()).toBeNull();
});

test("closing the notice puts the two actions back at the top right", async () => {
  await start([TEAM]);
  fireEvent.click(within(notice()!).getByRole("button", { name: "Close this notice" }));
  expect(notice()).toBeNull();
  expect(within(topRight()!).getByRole("button", { name: "Sign in" })).toBeTruthy();
});

test("signed in: the username, Sign out and Delete account at the top right, and no notice", async () => {
  await start([TEAM], "ash");
  expect(topRight()!.textContent).toBe("ashSign outDelete account");
  expect(notice()).toBeNull();
});

test.each([
  { form: "Create account", autocomplete: "new-password", link: "Have one? Sign in", other: "Sign in" },
  { form: "Sign in", autocomplete: "current-password", link: "New here? Create account", other: "Create account" },
] as const)("the $form dialog has its parts and links to the other form", async ({ form, autocomplete, link, other }) => {
  await start();
  openDialog(form);
  expect(dialog().getByRole("heading").textContent).toBe(form);
  expect(dialog().getByLabelText("Username").getAttribute("autocomplete")).toBe("username");
  const password = dialog().getByLabelText("Password");
  expect([password.getAttribute("type"), password.getAttribute("autocomplete")]).toEqual(["password", autocomplete]);
  expect(dialog().getByText("There is no email, so a forgotten password can't be reset.")).toBeTruthy();
  expect(dialog().getByRole("button", { name: form }).getAttribute("type")).toBe("submit");
  fireEvent.click(dialog().getByRole("button", { name: link }));
  expect(dialog().getByRole("heading").textContent).toBe(other);
});

const MERGE = "Teams in this browser will be added to your account. An account holds at most 20; any beyond that are not kept.";

test.each([
  { teams: [TEAM], shown: true },
  { teams: [], shown: false },
])("the sign-in dialog warns about merging only when this browser has teams ($shown)", async ({ teams, shown }) => {
  await start(teams);
  if (teams.length) fireEvent.click(within(notice()!).getByRole("button", { name: "Close this notice" }));
  openDialog("Sign in");
  expect(dialog().queryByText(MERGE) !== null).toBe(shown);
});

test.each([
  { status: 409, detail: "That username is taken.", form: "Create account" },
  { status: 422, detail: "Passwords need at least 8 characters.", form: "Create account" },
  { status: 401, detail: "Wrong username or password.", form: "Sign in" },
  { status: 503, detail: "Too many sign-ins at once. Try again.", form: "Sign in" },
] as const)("a $status shows the server's sentence and the dialog stays open", async ({ status, detail, form }) => {
  const server = await start();
  openDialog(form);
  server.refuseNext("POST", status, undefined, form === "Sign in" ? "/api/session" : "/api/account", detail);
  await fillAndSubmit("ash", "pikachu-rules");
  expect(dialog().getByRole("alert").textContent).toBe(detail);
});

test("after signing in, the account's teams are loaded and the counts are shown", async () => {
  const server = await start([TEAM]);
  server.accountTeams = [{ id: 7, name: "Rain team", pokemon_ids: [9] }, TEAM];
  server.merged = { teams_added: 1, teams_not_added: 0 };
  openDialog("Sign in");
  await fillAndSubmit("ash", "pikachu-rules");
  expect(screen.queryByRole("dialog")).toBeNull();
  expect(screen.getByRole("button", { name: "Rain team" })).toBeTruthy();
  expect(document.querySelector(".notice-bar span")?.textContent).toBe(
    "Signed in as ash. 1 team from this browser added to your account.",
  );
  expect(topRight()!.textContent).toBe("ashSign outDelete account");
});

test("after signing out there are no teams, and the page is as for a first visit", async () => {
  await start([TEAM], "ash");
  await act(async () => fireEvent.click(within(topRight()!).getByRole("button", { name: "Sign out" })));
  expect(screen.queryByRole("button", { name: "Team 1" })).toBeNull();
  expect(screen.getByText("Build your first team")).toBeTruthy();
  expect(document.activeElement).toBe(within(topRight()!).getByRole("button", { name: "Create account" }));
});

test("Escape closes the dialog and focus returns to the control that opened it", async () => {
  await start();
  const opener = within(topRight()!).getByRole("button", { name: "Sign in" });
  opener.focus();
  fireEvent.click(opener);
  fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });
  expect(screen.queryByRole("dialog")).toBeNull();
  expect(document.activeElement).toBe(opener);
});

test("Tab from the dialog's last control goes back to its first", async () => {
  await start();
  openDialog("Sign in");
  const controls = screen.getByRole("dialog").querySelectorAll<HTMLElement>("input, button");
  controls[controls.length - 1]!.focus();
  fireEvent.keyDown(screen.getByRole("dialog"), { key: "Tab" });
  expect(document.activeElement).toBe(controls[0]);
});

test("a second submit while the first is in flight sends nothing more", async () => {
  const server = await start();
  openDialog("Sign in");
  const release = server.hold();
  fillIn("ash", "pikachu-rules");
  const form = dialog().getByLabelText("Username").closest("form")!;
  fireEvent.submit(form);
  fireEvent.submit(form);
  await act(async () => release());
  expect(server.calls.filter((call) => call.path === "/api/session" && call.method === "POST")).toHaveLength(1);
});

// ---- Deleting the account.

const deleteForm = () => within(screen.getByRole("dialog", { name: "Delete account" }));

async function openDelete() {
  const server = await start([TEAM], "ash");
  fireEvent.click(within(topRight()!).getByRole("button", { name: "Delete account" }));
  return server;
}

const deleteRequests = (server: FakeServer) => server.calls.filter((call) => call.path === "/api/account/delete");

test("Delete account is offered only when signed in", async () => {
  await start();
  expect(screen.queryByRole("button", { name: "Delete account" })).toBeNull();
});

test("the delete dialog names the account, asks for its password and says it cannot be undone", async () => {
  await openDelete();
  expect(
    deleteForm().getByText("This deletes the account ash, its teams and its sign-ins on every device. It cannot be undone."),
  ).toBeTruthy();
  const password = deleteForm().getByLabelText("Password");
  expect([password.getAttribute("type"), password.getAttribute("autocomplete")]).toEqual(["password", "current-password"]);
});

test("a wrong password shows the server's sentence and keeps the dialog open", async () => {
  const server = await openDelete();
  server.refuseNext("POST", 401, undefined, "/api/account/delete", "Wrong password.");
  fireEvent.change(deleteForm().getByLabelText("Password"), { target: { value: "nope-nope" } });
  await act(async () => fireEvent.click(deleteForm().getByRole("button", { name: "Delete account" })));
  expect(deleteForm().getByRole("alert").textContent).toBe("Wrong password.");
});

test.each([
  { close: "Cancel", act: () => fireEvent.click(deleteForm().getByRole("button", { name: "Cancel" })) },
  { close: "Escape", act: () => fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" }) },
])("$close closes the delete dialog, sends nothing and returns focus to the link", async ({ act: close }) => {
  const server = await start([TEAM], "ash");
  const link = within(topRight()!).getByRole("button", { name: "Delete account" });
  link.focus();
  fireEvent.click(link);
  close();
  expect(screen.queryByRole("dialog")).toBeNull();
  expect(deleteRequests(server)).toEqual([]);
  expect(document.activeElement).toBe(link);
});

test("after deleting, the page is as for a first visit and says the account was deleted", async () => {
  const server = await openDelete();
  fireEvent.change(deleteForm().getByLabelText("Password"), { target: { value: "pikachu-rules" } });
  await act(async () => fireEvent.click(deleteForm().getByRole("button", { name: "Delete account" })));
  expect(deleteRequests(server).map((call) => call.body)).toEqual([{ password: "pikachu-rules" }]);
  expect(screen.queryByRole("dialog")).toBeNull();
  expect(screen.getByText("Build your first team")).toBeTruthy();
  expect(within(topRight()!).getAllByRole("button").map((b) => b.textContent)).toEqual(["Create account", "Sign in"]);
  expect(document.querySelector(".notice-bar span")?.textContent).toBe("Your account was deleted.");
});
