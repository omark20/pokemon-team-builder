import { expect, test } from "vitest";
import { accountErrorText, signedInText } from "./account";
import { ApiError } from "./api";

test.each([
  { added: 0, notAdded: 0, renamed: 0, text: "Signed in as ash." },
  { added: 1, notAdded: 0, renamed: 0, text: "Signed in as ash. 1 team from this browser added to your account." },
  {
    added: 3,
    notAdded: 2,
    renamed: 0,
    text: "Signed in as ash. 3 teams from this browser added to your account. 2 teams not kept: an account holds at most 20.",
  },
  {
    added: 2,
    notAdded: 0,
    renamed: 1,
    text: "Signed in as ash. 2 teams from this browser added to your account. 1 was renamed because you already had a team with that name.",
  },
  {
    added: 3,
    notAdded: 0,
    renamed: 2,
    text: "Signed in as ash. 3 teams from this browser added to your account. 2 were renamed because you already had teams with those names.",
  },
])("after signing in with $added added, $renamed renamed and $notAdded not kept", ({ added, notAdded, renamed, text }) => {
  const answer = { username: "ash", teams_added: added, teams_not_added: notAdded, teams_renamed: renamed };
  expect(signedInText(answer)).toBe(text);
});

test.each([
  { status: 429, retryAfter: 30, detail: "Too many sign-in attempts.", text: "Too many sign-in attempts. Try again in 30 seconds." },
  { status: 429, retryAfter: 600, detail: null, text: "Too many attempts. Try again in 10 minutes." },
  { status: 429, retryAfter: 61, detail: null, text: "Too many attempts. Try again in 2 minutes." },
  { status: 429, retryAfter: 643, detail: "Too many requests", text: "Too many requests. Try again in 11 minutes." },
])("a 429 says when to try again ($retryAfter s)", ({ status, retryAfter, detail, text }) => {
  expect(accountErrorText(new ApiError(status, retryAfter, detail))).toBe(text);
});
