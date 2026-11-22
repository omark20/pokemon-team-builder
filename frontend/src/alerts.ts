// The visitor's change alerts: loaded once when the page opens, and dismissed
// one at a time with the existing per-alert call. "Dismiss all" makes that
// call for each alert in turn and stops at the first refusal, leaving the rest.
import { useCallback, useEffect, useState } from "react";
import { dismissAlert, fetchAlerts } from "./api";
import type { Alert } from "./types";

export const ALERT_MESSAGES = {
  loadFailed: "Couldn't check for changes to your Pokémon.",
  dismissFailed: "Couldn't dismiss that alert. Try again.",
  dismissAllStopped: "Couldn't dismiss every alert; the rest are still here. Try again.",
};

export interface AlertsState {
  alerts: Alert[];
  failed: boolean; // the alerts could not be loaded
  message: string | null; // why the last dismissal did not go through
}

export function useAlerts() {
  const [state, setState] = useState<AlertsState>({ alerts: [], failed: false, message: null });

  const load = useCallback(async () => {
    try {
      setState({ alerts: await fetchAlerts(), failed: false, message: null });
    } catch {
      setState({ alerts: [], failed: true, message: null });
    }
  }, []);
  useEffect(() => void load(), [load]);

  // True when the alert was dismissed; it then leaves the list.
  async function dismiss(id: number, refusal = ALERT_MESSAGES.dismissFailed): Promise<boolean> {
    try {
      await dismissAlert(id);
    } catch {
      setState((current) => ({ ...current, message: refusal }));
      return false;
    }
    setState((current) => ({ ...current, message: null, alerts: current.alerts.filter((a) => a.id !== id) }));
    return true;
  }

  async function dismissAll(ids: number[]): Promise<void> {
    for (const id of ids) {
      if (!(await dismiss(id, ALERT_MESSAGES.dismissAllStopped))) return;
    }
  }

  return { ...state, load, dismiss, dismissAll };
}
