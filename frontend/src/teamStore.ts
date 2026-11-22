// The visitor's teams and every change to them, kept outside the components so
// each rule is one short method that can be tested without drawing the page.
//
// A change to a team's members shows at once and is saved in the background,
// one request at a time per team, each carrying the complete list. If a save
// fails the team goes back to what the server last confirmed.
import { useSyncExternalStore } from "react";
import { ApiError, createTeam, deleteTeam, fetchCounter, fetchTeams, renameTeam, saveMembers } from "./api";
import { TEAM_SIZE } from "./teamMoves";
import { displayName, type CounterResult, type Pokemon, type Team } from "./types";

export interface Notice {
  kind: "info" | "error";
  text: string;
}

export interface TeamsState {
  status: "loading" | "failed" | "ready";
  teams: Team[];
  activeId: number | null; // the team whose tab is selected
  creating: boolean; // a team is being created; other adds and creates wait
  notice: Notice | null;
  // The counter team of the selected team, built on request. It is cleared
  // whenever that team's members change or another tab is selected, so what
  // is shown always answers the team on screen.
  counter: CounterResult | null;
  building: boolean; // a counter team is being worked out
}

export const MESSAGES = {
  teamFull: "This team already has six Pokémon. Remove one to add another.",
  saveFailed: "Couldn't save your team. Your change was undone.",
  tooFastSeconds: "You're going a little fast. Try again in a few seconds.",
  tooFastMinutes: "You're going a little fast. Try again in a few minutes.",
  createFailed: "Couldn't create the team. Try again.",
  tooManyTeams: "You already have 20 teams. Delete one to make another.",
  renameFailed: "Couldn't rename the team. Try again.",
  deleteFailed: "Couldn't delete the team. Try again.",
  counterFailed: "Couldn't build the counter team. Try again.",
  noTypeChart: "The type chart is not loaded yet, so no counter team can be built. Try again later.",
  halfDone: (team: string) =>
    `${team} was created, but the Pokémon could not be added. Press Add again.`,
};

// A "too many requests" answer gets its own message, by how long the wait is:
// the hourly limit on new visitors is minutes away, the others seconds.
function errorText(error: unknown, fallback: string): string {
  if (!(error instanceof ApiError) || error.status !== 429) return fallback;
  return error.retryAfter > 60 ? MESSAGES.tooFastMinutes : MESSAGES.tooFastSeconds;
}

// A 503 from the counter endpoint means the type chart has not been loaded.
function counterErrorText(error: unknown): string {
  const noChart = error instanceof ApiError && error.status === 503;
  return noChart ? MESSAGES.noTypeChart : MESSAGES.counterFailed;
}

// "Team" and the next number after the highest one in use: "Team 1" first.
export function nextTeamName(teams: Team[]): string {
  const numbers = teams.map((team) => Number(/^Team (\d+)$/.exec(team.name)?.[1] ?? 0));
  return `Team ${Math.max(0, ...numbers) + 1}`;
}

export class TeamStore {
  private state: TeamsState = {
    status: "loading",
    teams: [],
    activeId: null,
    creating: false,
    notice: null,
    counter: null,
    building: false,
  };
  private readonly listeners = new Set<() => void>();
  // Per team: the members the server last confirmed, the newest members not
  // yet sent, and whether a save is in flight.
  private readonly confirmed = new Map<number, number[]>();
  private readonly unsent = new Map<number, number[]>();
  private readonly saving = new Map<number, Promise<void>>();

  subscribe = (listener: () => void) => {
    this.listeners.add(listener);
    return () => void this.listeners.delete(listener);
  };

  getState = () => this.state;

  activeTeam(): Team | undefined {
    return this.state.teams.find((team) => team.id === this.state.activeId);
  }

  async load(): Promise<void> {
    this.update({ status: "loading" });
    try {
      const teams = await fetchTeams();
      for (const team of teams) this.confirmed.set(team.id, team.pokemon_ids);
      this.update({ status: "ready", teams, activeId: teams[0]?.id ?? null });
    } catch {
      this.update({ status: "failed" });
    }
  }

  select(id: number): void {
    this.update({ activeId: id, notice: null, counter: null });
  }

  dismissNotice(): void {
    this.update({ notice: null });
  }

  // The "New team" tab: an empty team with the next free name, selected.
  async newTeam(): Promise<void> {
    await this.whileCreating(() => this.postTeam());
  }

  async rename(id: number, name: string): Promise<void> {
    try {
      const saved = await renameTeam(id, name);
      this.changeTeam(id, { name: saved.name });
    } catch (error) {
      this.fail(error, MESSAGES.renameFailed);
    }
  }

  // Deletes a team and selects the tab that takes its place, if any.
  async remove(id: number): Promise<void> {
    try {
      await deleteTeam(id);
    } catch (error) {
      return this.fail(error, MESSAGES.deleteFailed);
    }
    const index = this.state.teams.findIndex((team) => team.id === id);
    const teams = this.state.teams.filter((team) => team.id !== id);
    const neighbour = teams[index] ?? teams[index - 1];
    const activeId = this.state.activeId === id ? (neighbour?.id ?? null) : this.state.activeId;
    this.update({ teams, activeId, notice: null, counter: null });
  }

  // Adds a Pokémon to the selected team; true when it was added. A visitor
  // with no team gets "Team 1" made first.
  async add(pokemon: Pokemon): Promise<boolean> {
    if (this.state.status !== "ready" || this.state.creating) return false;
    const team = this.activeTeam();
    if (!team) return (await this.createTeamWith([pokemon.id])) === true;
    if (team.pokemon_ids.length >= TEAM_SIZE) {
      this.update({ notice: { kind: "error", text: MESSAGES.teamFull } });
      return false;
    }
    this.setMembers(team.id, [...team.pokemon_ids, pokemon.id]);
    const text = `${displayName(pokemon.name)} added to ${team.name}.`;
    this.update({ notice: { kind: "info", text } });
    return true;
  }

  // Shows the new member list at once and saves it in the background.
  setMembers(id: number, pokemonIds: number[]): void {
    this.changeTeam(id, { pokemon_ids: pokemonIds });
    this.unsent.set(id, pokemonIds);
    if (!this.saving.has(id)) this.saving.set(id, this.saveUnsent(id));
  }

  // Asks the server for the selected team's counter team, once its latest
  // members are saved. An answer for members that changed meanwhile is dropped.
  async buildCounter(): Promise<void> {
    const team = this.activeTeam();
    if (!team?.pokemon_ids.length || this.state.building) return;
    this.update({ building: true, notice: null, counter: null });
    try {
      await this.saving.get(team.id);
      const asked = this.activeTeam()?.pokemon_ids;
      const counter = await fetchCounter(team.id);
      if (this.activeTeam()?.pokemon_ids === asked) this.update({ counter });
    } catch (error) {
      this.fail(error, counterErrorText(error));
    } finally {
      this.update({ building: false });
    }
  }

  // "Save as new team": the counter team becomes a team of its own.
  async saveCounterAsTeam(): Promise<void> {
    const ids = this.state.counter?.picks.map((pick) => pick.counter.id);
    if (ids) await this.createTeamWith(ids);
  }

  // Sends the newest unsent list, and again if a newer one arrived meanwhile,
  // so saves for one team never overlap and the last change always wins.
  private async saveUnsent(id: number): Promise<void> {
    try {
      for (let ids = this.unsent.get(id); ids; ids = this.unsent.get(id)) {
        this.unsent.delete(id);
        this.confirmed.set(id, (await saveMembers(id, ids)).pokemon_ids);
      }
    } catch (error) {
      this.unsent.delete(id);
      this.changeTeam(id, { pokemon_ids: this.confirmed.get(id) ?? [] });
      this.fail(error, MESSAGES.saveFailed);
    } finally {
      this.saving.delete(id);
    }
  }

  // A new team holding these Pokémon: two requests, create then set members.
  // Used by a first Add and by "Save as new team". If the second request
  // fails the new team stays, empty, and the message says so.
  private createTeamWith(pokemonIds: number[]): Promise<boolean | null> {
    return this.whileCreating(async () => {
      const team = await this.postTeam();
      if (!team) return false;
      try {
        const saved = await saveMembers(team.id, pokemonIds);
        this.confirmed.set(team.id, saved.pokemon_ids);
        this.changeTeam(team.id, { pokemon_ids: saved.pokemon_ids });
        return true;
      } catch {
        this.update({ notice: { kind: "error", text: MESSAGES.halfDone(team.name) } });
        return false;
      }
    });
  }

  // Runs one team-creating action at a time: a second one started while the
  // first is in flight does nothing, so two quick clicks cannot make two teams.
  private async whileCreating<T>(action: () => Promise<T>): Promise<T | null> {
    if (this.state.creating) return null;
    this.update({ creating: true, notice: null });
    try {
      return await action();
    } finally {
      this.update({ creating: false });
    }
  }

  private async postTeam(): Promise<Team | null> {
    try {
      const team = await createTeam(nextTeamName(this.state.teams));
      this.confirmed.set(team.id, team.pokemon_ids);
      this.update({ teams: [...this.state.teams, team], activeId: team.id, counter: null });
      return team;
    } catch (error) {
      const atLimit = error instanceof ApiError && error.status === 409;
      this.fail(error, atLimit ? MESSAGES.tooManyTeams : MESSAGES.createFailed);
      return null;
    }
  }

  // A change to a team's members also clears the counter team built for it.
  private changeTeam(id: number, change: Partial<Team>): void {
    const teams = this.state.teams.map((team) => (team.id === id ? { ...team, ...change } : team));
    const stale = change.pokemon_ids !== undefined && id === this.state.activeId;
    this.update({ teams, notice: null, counter: stale ? null : this.state.counter });
  }

  private fail(error: unknown, fallback: string): void {
    this.update({ notice: { kind: "error", text: errorText(error, fallback) } });
  }

  private update(change: Partial<TeamsState>): void {
    this.state = { ...this.state, ...change };
    for (const listener of this.listeners) listener();
  }
}

// The store's current state, re-read whenever the store changes.
export function useTeams(store: TeamStore): TeamsState {
  return useSyncExternalStore(store.subscribe, store.getState);
}
