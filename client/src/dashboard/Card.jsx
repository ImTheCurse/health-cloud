import Button from "@mui/material/Button";
import ButtonBase from "@mui/material/ButtonBase";
import Dialog from "@mui/material/Dialog";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import IconButton from "@mui/material/IconButton";
import CloseIcon from "@mui/icons-material/Close";
import { useState } from "react";

import CardLoading from "./CardLoading.jsx";
import ChartBoundary from "./ChartBoundary.jsx";
import { EXPLAIN } from "./explain.js";

/**
 * One chart: title, a legend whose entries switch series on and off, a "Learn
 * more" dialog, and its own loading, empty or error state, so a route that
 * fails blanks only its own card.
 *
 * - `states`: every `useData` result the chart draws from.
 * - `legend`: `[{ id, label, color, shape }]`; with `onToggle`, entries are buttons.
 * - `explain`: a key into `EXPLAIN`.
 */
export default function Card({
  title,
  note,
  legend,
  hidden,
  onToggle,
  explain,
  toolbar,
  states = [],
  empty = false,
  emptyText = "Nothing recorded in this range.",
  height = 240,
  wide = false,
  children,
}) {
  const [open, setOpen] = useState(false);
  const failed = states.find((state) => state.status === "error");
  const loading = states.some((state) => state.status === "loading");
  const showBody = !failed && !loading && !empty;
  const article = explain ? EXPLAIN[explain] : null;

  let body = <ChartBoundary resetKeys={states.map((state) => state.data)}>{children}</ChartBoundary>;
  if (failed) body = <p className="card-state alert">Couldn't load this: {failed.error.message}</p>;
  else if (loading) {
    body = height === "auto" ? <CardLoading shape="rows" /> : <CardLoading shape="chart" height={height} />;
  }
  else if (empty) body = <p className="card-state">{emptyText}</p>;

  return (
    <figure className={wide ? "card wide" : "card"}>
      <figcaption>
        <div className="card-head">
          <h2>{title}</h2>
          {article && (
            <Button size="small" variant="text" color="secondary" onClick={() => setOpen(true)}>
              Learn more
            </Button>
          )}
        </div>
        {note && <p className="card-note">{note}</p>}
        {showBody && toolbar}
        {showBody && legend && legend.length > 0 && (
          <Legend items={legend} hidden={hidden} onToggle={onToggle} />
        )}
      </figcaption>
      <div className="card-body" style={{ height: showBody && height !== "auto" ? height : undefined }}>
        {body}
      </div>
      {article && (
        <Dialog open={open} onClose={() => setOpen(false)} maxWidth="sm" fullWidth>
          <DialogTitle>{article.title ?? title}</DialogTitle>
          <IconButton
            aria-label="Close"
            onClick={() => setOpen(false)}
            sx={{ position: "absolute", right: 12, top: 12, border: 0 }}
          >
            <CloseIcon fontSize="small" />
          </IconButton>
          <DialogContent className="explain">
            {article.sections.map((section) => (
              <section key={section.heading}>
                <h3>{section.heading}</h3>
                <p>{section.text}</p>
              </section>
            ))}
            <p className="explain-disclaimer">
              General information, not medical advice. Your own trend matters more than
              anyone else's numbers; ask a doctor about anything that worries you.
            </p>
          </DialogContent>
        </Dialog>
      )}
    </figure>
  );
}

export function Legend({ items, hidden, onToggle }) {
  return (
    <ul className="legend">
      {items.map((item) => {
        const off = hidden?.has(item.id);
        const swatch = (
          <span
            className={`swatch ${item.shape ?? "block"}`}
            style={{ "--swatch": item.color }}
            aria-hidden="true"
          />
        );
        return (
          <li key={item.id ?? item.label}>
            {onToggle && item.id ? (
              <ButtonBase
                className={off ? "legend-item off" : "legend-item"}
                aria-pressed={!off}
                onClick={() => onToggle(item.id)}
              >
                {swatch}
                {item.label}
              </ButtonBase>
            ) : (
              <span className="legend-item static">
                {swatch}
                {item.label}
              </span>
            )}
          </li>
        );
      })}
    </ul>
  );
}
