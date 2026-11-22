import { expect, test } from "vitest";
import { accountErrorText, signedInText } from "./account";
import { ApiError } from "./api";

test.each([
  { added: 0, notAdded: 0, text: "Signed in as ash." },
  { added: 1, notAdded: 0, text: "Signed in as ash. 1 team from this browser added to your account." },
  {
    added: 3,
    notAdded: 2,
    text: "Signed in as ash. 3 teams from this browser added to your account. 2 teams not kept: an account holds at most 20.",
  },
])("after signing in with $added added and $notAdded not kept", ({ added, notAdded, text }) => {
  expect(signedInText("ash", added, notAdded)).toBe(text);
});

test.each([
  { status: 429, retryAfter: 30, detail: "Too many sign-in attempts.", text: "Too many sign-in attempts. Try again in 30 seconds." },
  { status: 429, retryAfter: 600, detail: null, text: "Too many attempts. Try again in 10 minutes." },
  { status: 429, retryAfter: 61, detail: null, text: "Too many attempts. Try again in 2 minutes." },
  { status: 429, retryAfter: 643, detail: "Too many requests", text: "Too many requests. Try again in 11 minutes." },
])("a 429 says when to try again ($retryAfter s)", ({ status, retryAfter, detail, text }) => {
  expect(accountErrorText(new ApiError(status, retryAfter, detail))).toBe(text);
});
