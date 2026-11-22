// A stand-in for the backend in tests. It answers the Pokémon list, the team,
// counter and alert endpoints and the scan status from memory, records every request, and can be told to
// refuse the next request or to hold it back until released.
import { vi } from "vitest";
import type { Alert, CounterResult, ScanRun, Team } from "../types";
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
  path?: string; // only a request to this path; any path when absent
  detail?: string; // the server's sentence, sent as {"detail": ...}
}

const json = (data: unknown, status = 200) => new Response(JSON.stringify(data), { status });

export class FakeServer {
  teams: Team[];
  counter: CounterResult = COUNTER; // the answer to every counter request
  alerts: Alert[] = [];
  runs: ScanRun[] = [];
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

  refuseNext(method: string, status: number, retryAfter?: number, path?: string, detail?: string): void {
    this.refusals.push({ method, status, retryAfter, path, detail });
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
    const refusal = this.refusals.find(
      (entry) => entry.method === method && (entry.path === undefined || entry.path === path),
    );
    if (!refusal) return this.answer(method, path, body);
    this.refusals = this.refusals.filter((entry) => entry !== refusal);
    const headers = refusal.retryAfter ? { "Retry-After": String(refusal.retryAfter) } : undefined;
    return new Response(JSON.stringify({ detail: refusal.detail }), { status: refusal.status, headers });
  }

  private answer(method: string, path: string, body: Call["body"]): Response {
    const [route, query] = path.split("?");
    if (route!.endsWith("/counter")) {
      return json({ ...this.counter, legendary_left_out: query === "leave_out_legendary=true" });
    }
    if (path.startsWith("/api/alerts")) return this.answerAlerts(method, path);
    if (path === "/api/scan/status") return json({ runs: this.runs, demo_active: false });
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

  private answerAlerts(method: string, path: string): Response {
    if (method === "GET") return json(this.alerts);
    const id = Number(path.split("/")[3]);
    this.alerts = this.alerts.filter((alert) => alert.id !== id);
    return new Response(null, { status: 204 });
  }
}
