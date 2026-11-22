// The dialog that deletes the signed-in account. It names the account, says it
// cannot be undone, and asks for the password. A refusal is shown inside and
// the dialog stays open; Cancel and Escape close it and send nothing.
import { useRef, useState, type FormEvent } from "react";
import type { Account } from "../account";
import { DialogFrame } from "./DialogFrame";

const deleteWarning = (username: string) =>
  `This deletes the account ${username}, its teams and its sign-ins on every device. It cannot be undone.`;

// Mounted only while open, so each opening starts with no message from the last.
export function DeleteAccountDialog({ account }: { account: Account }) {
  if (account.dialog !== "delete" || !account.username) return null;
  return <DeleteForm account={account} username={account.username} />;
}

function DeleteForm({ account, username }: { account: Account; username: string }) {
  const [problem, setProblem] = useState<string | null>(null);
  const busy = useRef(false); // a second press while one is in flight is ignored

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy.current) return;
    busy.current = true;
    setProblem(await account.deleteAccount(String(new FormData(event.currentTarget).get("password"))));
    busy.current = false;
  }
  return (
    <DialogFrame title="Delete account" onClose={account.close}>
      <form onSubmit={submit}>
        <p>{deleteWarning(username)}</p>
        <label>
          Password
          <input name="password" type="password" autoComplete="current-password" required autoFocus />
        </label>
        {problem && (
          <p className="dialog-error" role="alert">
            {problem}
          </p>
        )}
        <button type="submit" className="destructive">
          Delete account
        </button>
        <button type="button" onClick={account.close}>
          Cancel
        </button>
      </form>
    </DialogFrame>
  );
}
