// The dialog for creating an account or signing in: a username, a password,
// a sentence saying there is no email to reset a password, one primary action
// and a link to the other form. A refusal is shown inside and the dialog stays
// open. Escape closes it; while open, Tab keeps focus inside it.
import { useRef, useState, type FormEvent } from "react";
import type { Account } from "../account";
import { DialogFrame } from "./DialogFrame";

const FORMS = {
  create: { mode: "create", title: "Create account", password: "new-password", other: "signin", link: "Have one? Sign in" },
  signin: { mode: "signin", title: "Sign in", password: "current-password", other: "create", link: "New here? Create account" },
} as const;

const NO_RESET = "There is no email, so a forgotten password can't be reset.";
const TEAMS_MERGED =
  "Teams in this browser will be added to your account. An account holds at most 20; any beyond that are not kept.";

interface DialogProps {
  account: Account;
  hasTeams: boolean; // this browser has teams, which signing in would merge
}

// Mounted only while open, so each opening starts with no message from the last.
export function AccountDialog({ account, hasTeams }: DialogProps) {
  const mode = account.dialog;
  if (mode !== "create" && mode !== "signin") return null;
  return <EntryForm account={account} hasTeams={hasTeams} text={FORMS[mode]} />;
}

function EntryForm({ account, hasTeams, text }: DialogProps & { text: (typeof FORMS)[keyof typeof FORMS] }) {
  const [problem, setProblem] = useState<string | null>(null);
  // A submit while one is in flight is ignored. The button is not disabled,
  // since disabling the focused button would drop focus out of the dialog.
  const busy = useRef(false);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy.current) return;
    const fields = new FormData(event.currentTarget);
    busy.current = true;
    setProblem(await account.submit(text.mode, String(fields.get("username")), String(fields.get("password"))));
    busy.current = false;
  }
  return (
    <DialogFrame title={text.title} onClose={account.close}>
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
          {text.mode === "signin" && hasTeams && <p>{TEAMS_MERGED}</p>}
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
    </DialogFrame>
  );
}
