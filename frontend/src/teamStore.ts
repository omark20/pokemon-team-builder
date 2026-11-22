// The visitor's teams and every change to them, kept outside the components so
// each rule is one short method that can be tested without drawing the page.
//
// A change to a team's members shows at once and is saved in the background,
// one request at a time per team, each carrying the complete list. If a save
// fails the team goes back to what the server last confirmed.
import { useSyncExternalStore } from "react";
import { ApiError, createTeam, deleteTeam, fetchCounter, fetchTeams, renameTeam, saveMembers } from "./api";
import { counterErrorText, errorText, MESSAGES } from "./messages";
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
  // The counter team of the selected team, built on request. Selecting another
  // tab, changing the team's members, deleting it or changing the legendary
  // box clears it, and an answer or error for a build started before such a
  // change is dropped, so what is shown always answers the team and the box
  // on screen.
  counter: CounterResult | null;
  counterError: string | null; // why the last build gave no counter team
  building: boolean; // a counter team is being worked out for what is on screen
  leaveOutLegendary: boolean; // the visitor's tick; kept while the page is open
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
    counterError: null,
    building: false,
    leaveOutLegendary: false,
  };
  // Counts the builds and the changes that make a build's answer stale.
  private buildNumber = 0;
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

  // Loads the visitor's teams; also used after signing in or out, when the
  // teams on screen belong to someone else.
  async load(): Promise<void> {
    this.update({ status: "loading", ...this.clearCounter() });
    try {
      const teams = await fetchTeams();
      for (const team of teams) this.confirmed.set(team.id, team.pokemon_ids);
      this.update({ status: "ready", teams, activeId: teams[0]?.id ?? null });
    } catch {
      this.update({ status: "failed" });
    }
  }

  select(id: number): void {
    this.update({ activeId: id, notice: null, ...this.clearCounter() });
  }

  dismissNotice(): void {
    this.update({ notice: null });
  }

  // Shows a message from elsewhere on the page in the same notice bar.
  inform(notice: Notice): void {
    this.update({ notice });
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
    this.update({ teams, activeId, notice: null, ...this.clearCounter() });
  }

  // Adds a Pokémon to the selected team; true when it was added. A visitor
  // with no team gets "Team 1" made first.
  async add(pokemon: Pokemon): Promise<boolean> {
    const waiting = this.whyAddWaits();
    if (waiting) {
      this.update({ notice: { kind: "error", text: waiting } });
      return false;
    }
    const team = this.activeTeam();
    if (!team) return (await this.createTeamWith([pokemon.id], MESSAGES.halfDone)) === true;
    if (team.pokemon_ids.length >= TEAM_SIZE) {
      this.update({ notice: { kind: "error", text: MESSAGES.teamFull } });
      return false;
    }
    this.setMembers(team.id, [...team.pokemon_ids, pokemon.id]);
    const text = `${displayName(pokemon.name)} added to ${team.name}.`;
    this.update({ notice: { kind: "info", text } });
    return true;
  }

  // Why an Add cannot happen yet, or null when it can.
  private whyAddWaits(): string | null {
    if (this.state.status === "loading") return MESSAGES.teamsLoading;
    if (this.state.status === "failed") return MESSAGES.teamsFailed;
    return this.state.creating ? MESSAGES.stillCreating : null;
  }

  // Shows the new member list at once and saves it in the background.
  setMembers(id: number, pokemonIds: number[]): void {
    this.changeTeam(id, { pokemon_ids: pokemonIds });
    this.unsent.set(id, pokemonIds);
    if (!this.saving.has(id)) this.saving.set(id, this.saveUnsent(id));
  }

  // Asks the server for the selected team's counter team, once its latest
  // members are saved. If anything it was asked for changes before the answer
  // arrives (see `counter` above), the answer or error is dropped.
  async buildCounter(): Promise<void> {
    const team = this.activeTeam();
    if (!team?.pokemon_ids.length || this.state.building) return;
    this.update({ notice: null, ...this.clearCounter(), building: true });
    const build = this.buildNumber;
    const stillWanted = () => build === this.buildNumber;
    try {
      await this.saving.get(team.id);
      if (!stillWanted()) return;
      const counter = await fetchCounter(team.id, this.state.leaveOutLegendary);
      if (stillWanted()) this.update({ counter, building: false });
    } catch (error) {
      if (stillWanted()) this.update({ counterError: counterErrorText(error), building: false });
    }
  }

  // Ticking or unticking the box changes who may be picked, so like a change
  // to the team it clears the counter half; nothing is asked of the server.
  setLeaveOutLegendary(leaveOut: boolean): void {
    this.update({ leaveOutLegendary: leaveOut, ...this.clearCounter() });
  }

  // "Save as new team": the counter team becomes a team of its own.
  async saveCounterAsTeam(): Promise<void> {
    const ids = this.state.counter?.picks.map((pick) => pick.counter.id);
    if (ids) await this.createTeamWith(ids, MESSAGES.counterNotSaved);
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
      if (!this.state.teams.some((team) => team.id === id)) return; // deleted meanwhile
      this.changeTeam(id, { pokemon_ids: this.confirmed.get(id) ?? [] });
      this.fail(error, MESSAGES.saveFailed);
    } finally {
      this.saving.delete(id);
    }
  }

  // A new team holding these Pokémon: two requests, create then set members.
  // Used by a first Add and by "Save as new team". If the second request
  // fails the new team stays, empty, and `halfDone` says what to do next.
  private createTeamWith(pokemonIds: number[], halfDone: (team: string) => string): Promise<boolean | null> {
    return this.whileCreating(async () => {
      const team = await this.postTeam();
      if (!team) return false;
      try {
        const saved = await saveMembers(team.id, pokemonIds);
        this.confirmed.set(team.id, saved.pokemon_ids);
        this.changeTeam(team.id, { pokemon_ids: saved.pokemon_ids });
        return true;
      } catch {
        this.update({ notice: { kind: "error", text: halfDone(team.name) } });
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
      this.update({ teams: [...this.state.teams, team], activeId: team.id, ...this.clearCounter() });
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
    this.update({ teams, notice: null, ...(stale ? this.clearCounter() : {}) });
  }

  // An empty counter half, and any build still in flight made stale.
  private clearCounter(): Partial<TeamsState> {
    this.buildNumber += 1;
    return { counter: null, counterError: null, building: false };
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
