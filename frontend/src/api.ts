// Every call the page makes to the backend. The browser talks to this app's
// own API only; it never calls PokéAPI. The visitor is identified by a cookie
// the server sets, which the browser sends by itself.
import type { Alert, CounterResult, Pokemon, ScanRun, Team } from "./types";

// A request the server refused. `retryAfter` is the number of seconds in the
// Retry-After header, which a "too many requests" answer (429) carries; 0 if
// the header is absent.
export class ApiError extends Error {
  readonly status: number;
  readonly retryAfter: number;

  constructor(status: number, retryAfter: number) {
    super(`the server answered ${status}`);
    this.status = status;
    this.retryAfter = retryAfter;
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const sendsBody = body !== undefined;
  const response = await fetch(path, {
    method,
    headers: sendsBody ? { "Content-Type": "application/json" } : undefined,
    body: sendsBody ? JSON.stringify(body) : undefined,
  });
  if (!response.ok) {
    throw new ApiError(response.status, Number(response.headers.get("Retry-After")) || 0);
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

// Add, remove and reorder are all this one call: the complete list in order.
export const saveMembers = (id: number, pokemonIds: number[]) =>
  request<Team>("PUT", `/api/teams/${id}/members`, { pokemon_ids: pokemonIds });

export const deleteTeam = (id: number) => request<void>("DELETE", `/api/teams/${id}`);

// The best counter team for a saved team, worked out by the server.
export const fetchCounter = (id: number) => request<CounterResult>("GET", `/api/teams/${id}/counter`);

// Changes from the last seven days to the visitor's Pokémon, newest first.
export const fetchAlerts = () => request<Alert[]>("GET", "/api/alerts");

export const dismissAlert = (changeId: number) =>
  request<void>("POST", `/api/alerts/${changeId}/dismiss`);

// The most recent runs of the scan, newest first.
export const fetchScanStatus = () => request<{ runs: ScanRun[] }>("GET", "/api/scan/status");
