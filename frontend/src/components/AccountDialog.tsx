// The dialog for creating an account or signing in: a username, a password,
// a sentence saying there is no email to reset a password, one primary action
// and a link to the other form. A refusal is shown inside and the dialog stays
// open. Escape closes it; while open, Tab keeps focus inside it.
import { useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import type { Account, DialogMode } from "../account";

const FORMS = {
  create: { title: "Create account", password: "new-password", other: "signin", link: "Have one? Sign in" },
  signin: { title: "Sign in", password: "current-password", other: "create", link: "New here? Create account" },
} as const;

export const NO_RESET = "There is no email, so a forgotten password can't be reset.";
export const TEAMS_MERGED =
  "Teams in this browser will be added to your account. An account holds at most 20; any beyond that are not kept.";

// Tab from the last control goes to the first, and Shift+Tab from the first
// to the last, so focus never leaves the dialog.
function keepFocusInside(event: KeyboardEvent<HTMLElement>) {
  const controls = [...event.currentTarget.querySelectorAll<HTMLElement>("input, button:not(:disabled)")];
  const [first, last] = [controls[0], controls[controls.length - 1]];
  const leaving = event.shiftKey ? document.activeElement === first : document.activeElement === last;
  if (!leaving) return;
  event.preventDefault();
  (event.shiftKey ? last : first)?.focus();
}

interface DialogProps {
  account: Account;
  hasTeams: boolean; // this browser has teams, which signing in would merge
}

export function AccountDialog({ account, hasTeams }: DialogProps) {
  const [problem, setProblem] = useState<string | null>(null);
  // A submit while one is in flight is ignored. The button is not disabled,
  // since disabling the focused button would drop focus out of the dialog.
  const busy = useRef(false);
  const mode: DialogMode | null = account.dialog;
  if (!mode) return null;
  const text = FORMS[mode];

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy.current) return;
    const fields = new FormData(event.currentTarget);
    busy.current = true;
    setProblem(await account.submit(mode!, String(fields.get("username")), String(fields.get("password"))));
    busy.current = false;
  }
  function onKeyDown(event: KeyboardEvent<HTMLElement>) {
    if (event.key === "Escape") account.close();
    if (event.key === "Tab") keepFocusInside(event);
  }
  return (
    <div className="dialog-backdrop">
      <div className="dialog" role="dialog" aria-modal="true" aria-labelledby="account-title" onKeyDown={onKeyDown}>
        <h2 id="account-title">{text.title}</h2>
        <button type="button" className="dialog-close" aria-label="Close" onClick={account.close}>
          ×
        </button>
        <form onSubmit={submit}>
          <label>
            Username
            <input name="username" autoComplete="username" required autoFocus />
          </label>
          <label>
            Password
            <input name="password" type="password" autoComplete={text.password} required />
          </label>
          <p>{NO_RESET}</p>
          {mode === "signin" && hasTeams && <p>{TEAMS_MERGED}</p>}
          {problem && (
            <p className="dialog-error" role="alert">
              {problem}
            </p>
          )}
          <button type="submit" className="primary">
            {text.title}
          </button>
        </form>
        <button
          type="button"
          className="link-button"
          onClick={() => {
            setProblem(null);
            account.open(text.other);
          }}
        >
          {text.link}
        </button>
      </div>
    </div>
  );
}
