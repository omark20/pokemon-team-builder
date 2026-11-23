// Every call the page makes to the backend. The browser talks to this app's
// own API only; it never calls PokéAPI. The visitor is identified by a cookie
// the server sets, which the browser sends by itself.
import type { MoveChoices } from "./moveChoice";
import type { Alert, CounterResult, Members, Pokemon, ScanRun, Team } from "./types";

// A request the server refused. `retryAfter` is the number of seconds in the
// Retry-After header, which a "too many requests" answer (429) carries; 0 if
// the header is absent. `detail` is the server's own sentence, when it sent one.
export class ApiError extends Error {
  readonly status: number;
  readonly retryAfter: number;
  readonly detail: string | null;

  constructor(status: number, retryAfter: number, detail: string | null) {
    super(`the server answered ${status}`);
    this.status = status;
    this.retryAfter = retryAfter;
    this.detail = detail;
  }
}

// The `detail` text of an error answer such as {"detail": "Team not found"}.
async function detailOf(response: Response): Promise<string | null> {
  const body: unknown = await response.json().catch(() => null);
  const detail = (body as { detail?: unknown } | null)?.detail;
  return typeof detail === "string" ? detail : null;
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const sendsBody = body !== undefined;
  const response = await fetch(path, {
    method,
    headers: sendsBody ? { "Content-Type": "application/json" } : undefined,
    body: sendsBody ? JSON.stringify(body) : undefined,
  });
  if (!response.ok) {
    const retryAfter = Number(response.headers.get("Retry-After")) || 0;
    throw new ApiError(response.status, retryAfter, await detailOf(response));
  }
  return (response.status === 204 ? undefined : await response.json()) as T;
}

// The whole stored Pokémon list, loaded once when the page opens.
export const fetchPokemon = () => request<Pokemon[]>("GET", "/api/pokemon");

// The visitor's teams in the order they were made; empty for a new visitor.
export const fetchTeams = () => request<Team[]>("GET", "/api/teams");

// Creating a team is also what makes the server start remembering a visitor.
export const createTeam = (name: string) => request<Team>("POST", "/api/teams", { name });

export const renameTeam = (id: number, name: string) =>
  request<Team>("PATCH", `/api/teams/${id}`, { name });

// Add, remove, reorder and choosing moves are all this one call: the complete
// list in order, each slot's chosen moves as their IDs (null for the usual four).
export const saveMembers = (id: number, members: Members) =>
  request<Team>("PUT", `/api/teams/${id}/members`, {
    pokemon_ids: members.pokemon_ids,
    move_ids: members.moves.map((moves) => moves?.map((move) => move.id) ?? null),
  });

// The moves a Pokémon may use in a fight, and its usual four.
export const fetchMoves = (pokemonId: number) => request<MoveChoices>("GET", `/api/pokemon/${pokemonId}/moves`);

export const deleteTeam = (id: number) => request<void>("DELETE", `/api/teams/${id}`);

// The best counter team for a saved team, worked out by the server, optionally
// with legendary and mythical Pokémon left out of the candidates.
// `leaveOut` names Pokémon the answer may not pick: every counter already shown.
export function fetchCounter(id: number, leaveOutLegendary: boolean, leaveOut: number[]) {
  const query = new URLSearchParams();
  if (leaveOutLegendary) query.set("leave_out_legendary", "true");
  for (const pokemonId of leaveOut) query.append("leave_out", String(pokemonId));
  const text = query.toString();
  return request<CounterResult>("GET", `/api/teams/${id}/counter${text ? `?${text}` : ""}`);
}

// Changes from the last seven days to the visitor's Pokémon, newest first.
export const fetchAlerts = () => request<Alert[]>("GET", "/api/alerts");

export const dismissAlert = (changeId: number) =>
  request<void>("POST", `/api/alerts/${changeId}/dismiss`);

// The most recent runs of the scan, newest first.
export const fetchScanStatus = () => request<{ runs: ScanRun[] }>("GET", "/api/scan/status");

// Who this browser is signed in as, or null for an anonymous visitor.
export const fetchSession = () => request<{ username: string | null }>("GET", "/api/session");

interface SignedIn {
  username: string;
  teams_added: number; // this browser's teams moved into the account
  teams_not_added: number; // this browser's teams beyond the account's 20, not kept
}

export const createAccount = (username: string, password: string) =>
  request<{ username: string }>("POST", "/api/account", { username, password });

export const signIn = (username: string, password: string) =>
  request<SignedIn>("POST", "/api/session", { username, password });

export const signOut = () => request<void>("DELETE", "/api/session");

// Deletes the signed-in account, its teams and its sessions; needs its password.
export const deleteAccount = (password: string) =>
  request<void>("POST", "/api/account/delete", { password });
