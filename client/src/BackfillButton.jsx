import Button from "@mui/material/Button";
import Tooltip from "@mui/material/Tooltip";
import { useEffect, useState } from "react";

import { fetchBackfill, startBackfill } from "./api.js";
import { refreshAll } from "./dashboard/dataStore.js";

// How often a running backfill is asked about. A run takes two to three minutes.
const POLL_MS = 10 * 1000;
// How long "Backfilled" stays before the button offers itself again.
const DONE_MS = 4 * 1000;

const IDLE = "idle";
const RUNNING = "running";
const DONE = "done";
const FAILED = "failed";
const UNAVAILABLE = "unavailable";

const LABEL = {
  [IDLE]: "Backfill today",
  [RUNNING]: "Backfilling…",
  [DONE]: "Backfilled",
  [FAILED]: "Backfill failed",
  [UNAVAILABLE]: "Backfill unavailable",
};

const HINT = {
  [IDLE]: "Fetch the last 24 hours from Google now. It also runs every hour.",
  [FAILED]: "The run failed. Its Prefect run names the types it could not fetch.",
  [UNAVAILABLE]: "The backfill could not be started or followed. Is Prefect running?",
};

// Styled as the account strip's other links, Renew and Sign out, from the theme
// those take their colours from.
const LINK = (theme) => ({
  font: "inherit",
  lineHeight: "inherit",
  minWidth: 0,
  padding: 0,
  verticalAlign: "baseline",
  color: theme.palette.text.primary,
  textDecoration: "underline",
  textDecorationColor: theme.palette.divider,
  textUnderlineOffset: "3px",
  "&:hover": {
    background: "none",
    textDecoration: "underline",
    textDecorationColor: theme.palette.secondary.main,
  },
  "&.Mui-disabled": { color: theme.palette.text.secondary, textDecoration: "none" },
});

/**
 * Starts a backfill of the last day and follows it, refreshing every chart once
 * the run has completed. The run is not remembered across a reload; clicking
 * again then queues a second run behind the first, which is harmless.
 */
export default function BackfillButton() {
  const [status, setStatus] = useState(IDLE);
  const [runId, setRunId] = useState(null);

  useEffect(() => {
    if (runId === null) return undefined;
    let cancelled = false;

    const check = async () => {
      try {
        const run = await fetchBackfill(runId);
        if (cancelled || !run || run.state === RUNNING) return;
        setRunId(null);
        if (run.state === "completed") {
          setStatus(DONE);
          refreshAll();
        } else {
          setStatus(FAILED);
        }
      } catch {
        if (cancelled) return;
        setRunId(null);
        setStatus(UNAVAILABLE);
      }
    };

    const timer = window.setInterval(check, POLL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [runId]);

  useEffect(() => {
    if (status !== DONE) return undefined;
    const timer = window.setTimeout(() => setStatus(IDLE), DONE_MS);
    return () => window.clearTimeout(timer);
  }, [status]);

  const start = async () => {
    setStatus(RUNNING);
    try {
      const started = await startBackfill();
      if (!started?.run_id) throw new Error("no run id");
      setRunId(started.run_id);
    } catch {
      setStatus(UNAVAILABLE);
    }
  };

  const busy = status === RUNNING || status === DONE;
  const button = (
    <Button variant="text" sx={LINK} onClick={start} disabled={busy}>
      {LABEL[status]}
    </Button>
  );

  return HINT[status] ? (
    <Tooltip title={HINT[status]}>{button}</Tooltip>
  ) : (
    button
  );
}
