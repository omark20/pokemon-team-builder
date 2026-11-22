// What the page says when a team action cannot be done, in one place.
import { ApiError } from "./api";

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
  halfDone: (team: string) =>
    `${team} was created, but the Pokémon could not be added. Press Add again.`,
  counterNotSaved: (team: string) =>
    `${team} was created, but the counter team could not be saved into it. Build it again and press Save as new team.`,
  stillCreating: "Wait a moment: a team is still being created.",
  teamsLoading: "Your teams are still loading. Try again in a moment.",
  teamsFailed: "Your teams could not be loaded. Press Try again above, then add.",
};

// A "too many requests" answer gets its own message, by how long the wait is:
// the hourly limit on new visitors is minutes away, the others seconds.
export function errorText(error: unknown, fallback: string): string {
  if (!(error instanceof ApiError) || error.status !== 429) return fallback;
  return error.retryAfter > 60 ? MESSAGES.tooFastMinutes : MESSAGES.tooFastSeconds;
}

// A 503 from the counter endpoint says in its own words what is missing (the
// type chart, the legendary flags) or that it is busy; the page shows that.
export function counterErrorText(error: unknown): string {
  const unavailable = error instanceof ApiError && error.status === 503 && error.detail;
  return unavailable || errorText(error, MESSAGES.counterFailed);
}
