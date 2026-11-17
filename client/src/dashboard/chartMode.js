// How a group's cards are drawn: as compact previews on the group page, or one
// chart in full on its own page. Cards and charts read it from context, so the
// groups render the same tree either way.

import { createContext, useContext } from "react";

/**
 * - `mode`: "preview" or "detail".
 * - `chart`: in detail, the `explain` key of the cards shown; the rest render nothing.
 * - `onOpen(key)`: in preview, opens a card's detail page.
 */
export const ChartModeContext = createContext({ mode: "detail", chart: null, onOpen: null });

export function useChartMode() {
  return useContext(ChartModeContext);
}

/** Whether charts should leave out their reference lines and ringed extremes. */
export function usePreview() {
  return useContext(ChartModeContext).mode === "preview";
}

const PREVIEW_SCALE = 0.7;
const DETAIL_SCALE = 1.6;

/** A card's body height in each mode; "auto" stays "auto". */
export function scaledHeight(height, mode) {
  if (typeof height !== "number") return height;
  return Math.round(height * (mode === "preview" ? PREVIEW_SCALE : DETAIL_SCALE));
}
