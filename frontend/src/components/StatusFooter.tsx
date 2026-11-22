// The line at the foot of the page saying when the scan last checked PokéAPI
// for changes, and what it found.
import { useEffect, useState } from "react";
import { fetchScanStatus } from "../api";
import type { ScanRun } from "../types";

const when = (isoTime: string) =>
  new Date(isoTime).toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });

export function describeRun(run: ScanRun | undefined): string {
  if (!run) return "PokéAPI has not been checked for changes yet.";
  if (run.status === "running") return "Checking PokéAPI for changes now.";
  const checked = `PokéAPI last checked for changes ${when(run.finished_at ?? run.started_at)}`;
  if (run.status === "failed") return `${checked}; that check failed.`;
  const changes = `${run.changed} ${run.changed === 1 ? "change" : "changes"}`;
  return `${checked}: ${run.scanned.toLocaleString("en-US")} Pokémon scanned, ${changes} found.`;
}

export function StatusFooter() {
  const [text, setText] = useState<string | null>(null);
  useEffect(() => {
    fetchScanStatus().then(
      (status) => setText(describeRun(status.runs[0])),
      () => setText("Couldn't read when PokéAPI was last checked."),
    );
  }, []);
  return <footer className="status-footer">{text}</footer>;
}
