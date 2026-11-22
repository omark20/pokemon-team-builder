// The optional account: who this browser is signed in as, the account dialog,
// and the notice that teams are kept in this browser only. A visitor who never
// signs up stays anonymous, exactly as before.
import { useEffect, useRef, useState } from "react";
import { flushSync } from "react-dom";
import { ApiError, createAccount, deleteAccount, fetchSession, signIn, signOut } from "./api";
import type { Notice } from "./teamStore";

export type DialogMode = "create" | "signin" | "delete";
export type EntryMode = Exclude<DialogMode, "delete">;

export const ACCOUNT_DELETED = "Your account was deleted.";

// After signing in: what happened to the teams this browser had.
export function signedInText(username: string, added: number, notAdded: number): string {
  const teams = (count: number) => `${count} ${count === 1 ? "team" : "teams"}`;
  const parts = [`Signed in as ${username}.`];
  if (added > 0) parts.push(`${teams(added)} from this browser added to your account.`);
  if (notAdded > 0) parts.push(`${teams(notAdded)} not kept: an account holds at most 20.`);
  return parts.join(" ");
}

// How long to wait, from a Retry-After header in seconds.
function waitText(seconds: number): string {
  if (seconds < 60) return `${seconds} ${seconds === 1 ? "second" : "seconds"}`;
  const minutes = Math.ceil(seconds / 60);
  return `${minutes} ${minutes === 1 ? "minute" : "minutes"}`;
}

// The sentence the dialog shows for a refusal: the server's own words (the
// name is taken, the rule a password broke, wrong username or password), and
// for too many attempts when to try again.
export function accountErrorText(error: unknown): string {
  if (!(error instanceof ApiError)) return "Couldn't reach the server. Try again.";
  if (error.status !== 429) return error.detail ?? "Something went wrong. Try again.";
  const wait = error.retryAfter > 0 ? ` Try again in ${waitText(error.retryAfter)}.` : " Try again later.";
  const said = error.detail ?? "Too many attempts.";
  return `${/[.!?]$/.test(said) ? said : `${said}.`}${wait}`; // the server's sentence may lack a full stop
}

interface AccountEvents {
  reload: () => Promise<void>; // the teams and alerts on screen now belong to someone else
  notify: (notice: Notice | null) => void; // null clears the message on screen
}

// Signs up or in: the account's name, and the sentence that reports it.
async function enter(mode: EntryMode, name: string, password: string) {
  if (mode === "create") {
    const made = await createAccount(name, password);
    return { username: made.username, text: `Account created. Signed in as ${made.username}.` };
  }
  const done = await signIn(name, password);
  return { username: done.username, text: signedInText(done.username, done.teams_added, done.teams_not_added) };
}

// Asks the server once who this browser is; undefined until it answers.
function useUsername() {
  const [username, setUsername] = useState<string | null | undefined>(undefined);
  useEffect(() => {
    fetchSession().then(
      (session) => setUsername(session.username),
      () => setUsername(null),
    );
  }, []);
  return [username, setUsername] as const;
}

// Which form the dialog shows, if any. Closing it puts focus back on what
// opened it, or on the account links when that is gone (the notice goes once
// the visitor is signed in).
function useDialog() {
  const [dialog, setDialog] = useState<DialogMode | null>(null);
  const opener = useRef<HTMLElement | null>(null);
  function open(mode: DialogMode) {
    if (!dialog) opener.current = document.activeElement as HTMLElement | null;
    setDialog(mode);
  }
  function close() {
    flushSync(() => setDialog(null));
    const back = opener.current?.isConnected ? opener.current : document.querySelector<HTMLElement>(".account-links button");
    back?.focus();
  }
  return { dialog, open, close };
}

// What the account's actions change on the page.
interface AccountContext extends AccountEvents {
  setUsername: (username: string | null) => void;
  setNoticeClosed: (closed: boolean) => void;
  close: () => void; // closes the dialog
}

// After signing out or deleting the account: the page as for a first visit,
// with focus on the account links, since what had it is gone.
async function becomeAnonymous(page: AccountContext) {
  await page.reload(); // no teams now, so the links, not the notice, show next
  flushSync(() => {
    page.setUsername(null);
    page.setNoticeClosed(false);
  });
  document.querySelector<HTMLElement>(".account-links button")?.focus();
}

// Signs up or in; resolves to the sentence to show in the dialog, or null when done.
async function submitEntry(page: AccountContext, mode: EntryMode, name: string, password: string) {
  try {
    const entered = await enter(mode, name, password);
    page.setUsername(entered.username);
    page.close();
    await page.reload();
    page.notify({ kind: "info", text: entered.text });
    return null;
  } catch (error) {
    return accountErrorText(error);
  }
}

async function signOutHere(page: AccountContext) {
  try {
    await signOut();
  } catch {
    return page.notify({ kind: "error", text: "Couldn't sign out. Try again." });
  }
  await becomeAnonymous(page);
}

// Deletes the account; resolves to the sentence to show in the dialog, or null when done.
async function deleteHere(page: AccountContext, password: string) {
  try {
    await deleteAccount(password);
  } catch (error) {
    return accountErrorText(error);
  }
  page.close();
  await becomeAnonymous(page);
  page.notify({ kind: "info", text: ACCOUNT_DELETED });
  return null;
}

export function useAccount(events: AccountEvents) {
  const [username, setUsername] = useUsername();
  const { dialog, open, close } = useDialog();
  const [noticeClosed, setNoticeClosed] = useState(false);
  const page: AccountContext = { ...events, setUsername, setNoticeClosed, close };
  function closeNotice() {
    flushSync(() => setNoticeClosed(true));
    document.querySelector<HTMLElement>(".account-links button")?.focus(); // the actions moved there
  }
  return {
    username,
    dialog,
    noticeClosed,
    // A message from before (such as "Signed in as …") would contradict the
    // dialog, so opening one clears it.
    open: (mode: DialogMode) => {
      events.notify(null);
      open(mode);
    },
    close,
    closeNotice,
    submit: (mode: EntryMode, name: string, password: string) => submitEntry(page, mode, name, password),
    signOut: () => signOutHere(page),
    deleteAccount: (password: string) => deleteHere(page, password),
  };
}

export type Account = ReturnType<typeof useAccount>;
