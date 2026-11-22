// The account's two places on the page. At the top right: "Create account"
// and "Sign in", or, when signed in, the username, "Sign out" and a quieter
// "Delete account". Above the teams, for a visitor who is not signed in and
// has a team: a notice that the teams are saved in this browser only, with the
// same two actions; while it shows, the top-right links do not.
import type { Account } from "../account";

const BROWSER_ONLY = "Your teams are saved in this browser only.";

// Whether the notice above the teams shows.
function noticeShows(account: Account, hasTeams: boolean): boolean {
  return account.username === null && hasTeams && !account.noticeClosed;
}

function SignUpOrIn({ account }: { account: Account }) {
  return (
    <>
      <button type="button" className="link-button" onClick={() => account.open("create")}>
        Create account
      </button>
      <button type="button" className="link-button" onClick={() => account.open("signin")}>
        Sign in
      </button>
    </>
  );
}

export function AccountLinks({ account, hasTeams }: { account: Account; hasTeams: boolean }) {
  if (account.username === undefined || noticeShows(account, hasTeams)) return null;
  return (
    <nav className="account-links" aria-label="Account">
      {account.username === null ? (
        <SignUpOrIn account={account} />
      ) : (
        <>
          <span className="account-name">{account.username}</span>
          <button type="button" className="link-button" onClick={() => void account.signOut()}>
            Sign out
          </button>
          <button type="button" className="link-button quiet" onClick={() => account.open("delete")}>
            Delete account
          </button>
        </>
      )}
    </nav>
  );
}

export function AccountNotice({ account, hasTeams }: { account: Account; hasTeams: boolean }) {
  if (!noticeShows(account, hasTeams)) return null;
  return (
    <section className="account-notice" aria-label="Where your teams are saved">
      <p>{BROWSER_ONLY}</p>
      <SignUpOrIn account={account} />
      <button type="button" className="notice-close" aria-label="Close this notice" onClick={account.closeNotice}>
        ×
      </button>
    </section>
  );
}
