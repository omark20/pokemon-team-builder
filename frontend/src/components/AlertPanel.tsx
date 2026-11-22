// The change-alert panel at the top of the page: a headline count, then one
// row per change to the visitor's Pokémon from the last seven days, each with
// Dismiss, and "Dismiss all". The old value is struck through and the new one
// is bold. Shown only when there is something to say.
import { useEffect, useRef, type RefObject } from "react";
import { alertStyle } from "../colours";
import { ALERT_MESSAGES } from "../alerts";
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
      <button
        type="button"
        className="alert-dismiss"
        aria-label={`Dismiss: ${row.subject}, ${row.what}`}
        disabled={dismissing}
        onClick={() => onDismiss(alert.id)}
      >
        Dismiss
      </button>
    </li>
  );
}

const headline = (count: number) =>
  `${count} ${count === 1 ? "change" : "changes"} to your Pokémon this week`;

// The page title's id: focus goes there when the last alert is dismissed.
export const PAGE_TITLE_ID = "page-title";

// After a dismissal, focus goes to the Dismiss button that took the pressed
// one's place (or the one before it), or to the page title when none is left.
// Returns the function the panel calls when a dismissal is asked for.
function useFocusAfterDismiss(panel: RefObject<HTMLElement | null>, alerts: Alert[], dismissing: boolean) {
  const pressed = useRef<number | null>(null);
  useEffect(() => {
    if (pressed.current === null || dismissing) return;
    const buttons = panel.current?.querySelectorAll<HTMLElement>(".alert-row .alert-dismiss") ?? [];
    const target = buttons[Math.min(pressed.current, buttons.length - 1)] ?? document.getElementById(PAGE_TITLE_ID);
    pressed.current = null;
    target?.focus();
  }, [panel, alerts, dismissing]);
  return (index: number) => (pressed.current = index);
}

export function AlertPanel(props: PanelProps) {
  const { alerts, failed, message } = props;
  const panel = useRef<HTMLElement>(null);
  const willDismiss = useFocusAfterDismiss(panel, alerts, props.dismissing);
  if (alerts.length === 0 && !failed && !message) return null;
  return (
    <section ref={panel} className="alert-panel" style={alertStyle()} aria-label="Changes to your Pokémon">
      {failed ? (
        <p className="alert-headline">
          {ALERT_MESSAGES.loadFailed}{" "}
          <button type="button" className="alert-dismiss" onClick={props.onRetry}>
            Try again
          </button>
        </p>
      ) : (
        <div className="alert-headline">
          <strong>{headline(alerts.length)}</strong>
          {alerts.length > 0 && (
            <button
              type="button"
              className="alert-dismiss"
              disabled={props.dismissing}
              onClick={() => {
                willDismiss(0);
                props.onDismissAll();
              }}
            >
              Dismiss all
            </button>
          )}
        </div>
      )}
      {message && <p role="alert">{message}</p>}
      <ul className="alert-rows">
        {alerts.map((alert, index) => (
          <AlertRowView
            key={alert.id}
            alert={alert}
            teams={props.teams}
            pokemonById={props.pokemonById}
            dismissing={props.dismissing}
            onDismiss={(id) => {
              willDismiss(index);
              props.onDismiss(id);
            }}
          />
        ))}
      </ul>
    </section>
  );
}
