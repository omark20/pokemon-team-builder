// A stand-in for the backend in tests. It answers the Pokémon list and the
// team endpoints from memory, records every request, and can be told to
// refuse the next request or to hold it back until released.
import { vi } from "vitest";
import type { CounterResult, Team } from "../types";
import { CENSUS } from "./census";
import { COUNTER } from "./counterFixture";

interface Call {
  method: string;
  path: string;
  body: { name?: string; pokemon_ids?: number[] };
}

interface Refusal {
  method: string;
  status: number;
  retryAfter?: number;
}

const json = (data: unknown, status = 200) => new Response(JSON.stringify(data), { status });

export class FakeServer {
  teams: Team[];
  counter: CounterResult = COUNTER; // the answer to every counter request
  readonly calls: Call[] = [];
  private nextId: number;
  private refusals: Refusal[] = [];
  private gate: Promise<void> | null = null;

  constructor(teams: Team[] = []) {
    this.teams = teams.map((team) => ({ ...team }));
    this.nextId = Math.max(0, ...teams.map((team) => team.id)) + 1;
    vi.spyOn(globalThis, "fetch").mockImplementation((input, init) =>
      this.handle(String(input), init),
    );
  }

  // Requests that change something, as "METHOD path" and the body sent.
  writes(): [string, Call["body"]][] {
    const changing = this.calls.filter((call) => call.method !== "GET");
    return changing.map((call) => [`${call.method} ${call.path}`, call.body]);
  }

  refuseNext(method: string, status: number, retryAfter?: number): void {
    this.refusals.push({ method, status, retryAfter });
  }

  // The next request waits until the returned function is called.
  hold(): () => void {
    let release = () => {};
    this.gate = new Promise((resolve) => (release = resolve));
    return release;
  }

  private async handle(path: string, init?: RequestInit): Promise<Response> {
    const method = init?.method ?? "GET";
    const body = init?.body ? JSON.parse(String(init.body)) : {};
    this.calls.push({ method, path, body });
    const gate = this.gate;
    this.gate = null;
    await gate;
    const refusal = this.refusals.find((entry) => entry.method === method);
    if (!refusal) return this.answer(method, path, body);
    this.refusals = this.refusals.filter((entry) => entry !== refusal);
    const headers = refusal.retryAfter ? { "Retry-After": String(refusal.retryAfter) } : undefined;
    return new Response("{}", { status: refusal.status, headers });
  }

  private answer(method: string, path: string, body: Call["body"]): Response {
    if (path.endsWith("/counter")) return json(this.counter);
    if (method === "GET") return json(path === "/api/pokemon" ? CENSUS : this.teams);
    if (method === "POST") {
      const created = { id: this.nextId++, name: body.name ?? "", pokemon_ids: [] };
      this.teams.push(created);
      return json(created, 201);
    }
    const team = this.teams.find((entry) => entry.id === Number(path.split("/")[3]));
    if (!team) return json({}, 404);
    if (method === "DELETE") {
      this.teams = this.teams.filter((entry) => entry !== team);
      return new Response(null, { status: 204 });
    }
    Object.assign(team, body);
    return json(team);
  }
}
