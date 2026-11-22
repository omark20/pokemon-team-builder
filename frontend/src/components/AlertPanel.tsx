// The change-alert panel at the top of the page: a headline count, then one
// row per change to the visitor's Pokémon from the last seven days, each with
// Dismiss, and "Dismiss all". The old value is struck through and the new one
// is bold. Shown only when there is something to say.
import { alertStyle } from "../colours";
import { describeAlert } from "../alertText";
import type { Alert, Pokemon, Team } from "../types";

interface PanelProps {
  alerts: Alert[]; // only those touching a Pokémon on one of `teams`
  teams: Team[];
  pokemonById: Map<number, Pokemon>;
  failed: boolean;
  message: string | null;
  dismissing: boolean; // a dismissal is in flight; the buttons wait
  onDismiss: (id: number) => void;
  onDismissAll: () => void;
  onRetry: () => void;
}

type RowProps = Pick<PanelProps, "teams" | "pokemonById" | "dismissing" | "onDismiss"> & { alert: Alert };

function AlertRowView({ alert, teams, pokemonById, dismissing, onDismiss }: RowProps) {
  const row = describeAlert(alert, teams, pokemonById);
  return (
    <li className="alert-row">
      <div className="alert-text">
        <strong>{row.subject}</strong> · {row.what}
        {row.oldValue !== null && (
          <>
            {" · "}
            <s className="alert-old">{row.oldValue}</s> <b>{row.newValue}</b>
          </>
        )}
        {alert.is_demo && <span className="alert-demo">demo data</span>}
        <div className="alert-meta">
          {row.detected} · {row.affects}
        </div>
      </div>
      <button type="button" className="alert-dismiss" disabled={dismissing} onClick={() => onDismiss(alert.id)}>
        Dismiss
      </button>
    </li>
  );
}

const headline = (count: number) =>
  `${count} ${count === 1 ? "change" : "changes"} to your Pokémon this week`;

export function AlertPanel(props: PanelProps) {
  const { alerts, failed, message } = props;
  if (alerts.length === 0 && !failed && !message) return null;
  return (
    <section className="alert-panel" style={alertStyle()} aria-label="Changes to your Pokémon">
      {failed ? (
        <p className="alert-headline">
          Couldn't check for changes to your Pokémon.{" "}
          <button type="button" className="alert-dismiss" onClick={props.onRetry}>
            Try again
          </button>
        </p>
      ) : (
        <div className="alert-headline">
          <strong>{headline(alerts.length)}</strong>
          {alerts.length > 0 && (
            <button type="button" className="alert-dismiss" disabled={props.dismissing} onClick={props.onDismissAll}>
              Dismiss all
            </button>
          )}
        </div>
      )}
      {message && <p role="alert">{message}</p>}
      <ul className="alert-rows">
        {alerts.map((alert) => (
          <AlertRowView
            key={alert.id}
            alert={alert}
            teams={props.teams}
            pokemonById={props.pokemonById}
            dismissing={props.dismissing}
            onDismiss={props.onDismiss}
          />
        ))}
      </ul>
    </section>
  );
}
