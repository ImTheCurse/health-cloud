import Skeleton from "@mui/material/Skeleton";
import { SpinnerDotted } from "spinners-react";

import { RULE } from "./theme.js";

const SIGNAL = "#b4690e";

// Bar heights for the placeholder chart, as a share of the plot: varied enough
// to read as data, fixed so it does not flicker between renders.
const BAR_HEIGHTS = [0.45, 0.7, 0.55, 0.85, 0.4, 0.65, 0.75, 0.5, 0.9, 0.6, 0.35, 0.7];

const prefersStill =
  typeof window !== "undefined" &&
  window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

/**
 * What a card shows while its data is on the way: a skeleton in the shape of
 * what is coming -- a chart, or rows for figures, tables and lanes -- with a
 * dotted spinner over it.
 */
export default function CardLoading({ shape = "chart", height }) {
  return (
    <div className="card-loading" style={{ height }} role="status" aria-live="polite">
      <span className="visually-hidden">Loading</span>
      {shape === "chart" ? <ChartSkeleton /> : <RowsSkeleton />}
      <div className="card-loading-spinner">
        <SpinnerDotted size={44} thickness={140} speed={90} color={SIGNAL} still={prefersStill} />
      </div>
    </div>
  );
}

function ChartSkeleton() {
  return (
    <div className="skeleton-chart" aria-hidden="true">
      <div className="skeleton-axis">
        {[0, 1, 2, 3].map((tick) => (
          <Skeleton key={tick} variant="text" width={28} sx={{ bgcolor: RULE }} />
        ))}
      </div>
      <div className="skeleton-bars">
        {BAR_HEIGHTS.map((share, index) => (
          <Skeleton
            key={index}
            variant="rectangular"
            animation="wave"
            sx={{ height: `${share * 100}%`, flex: 1, borderRadius: "2px 2px 0 0", bgcolor: RULE }}
          />
        ))}
      </div>
    </div>
  );
}

function RowsSkeleton() {
  return (
    <div className="skeleton-rows" aria-hidden="true">
      {[0.9, 0.7, 0.8].map((share, index) => (
        <Skeleton key={index} variant="rounded" animation="wave" height={22} width={`${share * 100}%`} sx={{ bgcolor: RULE }} />
      ))}
    </div>
  );
}
