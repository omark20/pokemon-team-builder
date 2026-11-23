// The shape of the team store's state, what it starts as, and the small pure
// rules it uses: what a team's saved lists are and what a new team is called.
import type { CounterResult, Members, Team } from "./types";

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
  // "Show another team": which team is showing (1 is the best), and the Pokémon
  // left out to find it, every counter shown before it.
  teamNumber: number;
  leftOut: number[];
}

// The most teams one visitor or account may hold, as the server enforces it.
export const TEAM_LIMIT = 20;

// "Show another team" offers at most this many teams in all.
export const MOST_TEAMS = 10;

// A team's two saved lists, without its id and name.
export const membersOf = ({ pokemon_ids, moves }: Team): Members => ({ pokemon_ids, moves });

// "Team" and the next number after the highest one in use: "Team 1" first.
// Capitals are ignored, as the server ignores them when it keeps names apart, so
// a stored "team 5" gives "Team 6".
export function nextTeamName(teams: Team[]): string {
  const numbers = teams.map((team) => Number(/^team (\d+)$/i.exec(team.name)?.[1] ?? 0));
  return `Team ${Math.max(0, ...numbers) + 1}`;
}

// The state before the visitor's teams have loaded.
export const START: TeamsState = {
  status: "loading",
  teams: [],
  activeId: null,
  creating: false,
  notice: null,
  counter: null,
  counterError: null,
  building: false,
  leaveOutLegendary: false,
  teamNumber: 1,
  leftOut: [],
};
