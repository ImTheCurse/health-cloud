import { createTheme } from "@mui/material/styles";

import { INK, INK_SOFT, RULE } from "./theme.js";

const PAPER = "#e7ecee";
const SIGNAL = "#b4690e";
const CARD = "#f4f7f8";
const SANS = '"IBM Plex Sans", system-ui, sans-serif';

/**
 * MUI restyled to the page: paper and ink, IBM Plex, square corners, hairline
 * rules instead of shadows, the amber signal colour for focus and selection.
 */
export const muiTheme = createTheme({
  palette: {
    mode: "light",
    primary: { main: INK, contrastText: PAPER },
    secondary: { main: SIGNAL },
    text: { primary: INK, secondary: INK_SOFT },
    background: { default: PAPER, paper: CARD },
    divider: RULE,
  },
  shape: { borderRadius: 2 },
  typography: {
    fontFamily: SANS,
    button: { textTransform: "none", fontWeight: 500, letterSpacing: 0 },
  },
  components: {
    MuiButtonBase: { defaultProps: { disableRipple: true } },
    MuiButton: {
      styleOverrides: {
        root: { borderRadius: 0, boxShadow: "none", "&:hover": { boxShadow: "none" } },
        text: { padding: "2px 6px", minWidth: 0 },
      },
    },
    MuiTabs: {
      styleOverrides: {
        root: { minHeight: 40, borderBottom: `1px solid ${RULE}` },
        indicator: { backgroundColor: SIGNAL, height: 2 },
      },
    },
    MuiTab: {
      styleOverrides: {
        root: {
          minHeight: 40,
          padding: "8px 12px",
          fontSize: "0.9375rem",
          color: INK_SOFT,
          "&.Mui-selected": { color: INK },
          "&:hover": { color: INK },
          "&.Mui-focusVisible": { outline: `2px solid ${SIGNAL}`, outlineOffset: -2 },
        },
      },
    },
    MuiToggleButtonGroup: {
      styleOverrides: { root: { borderRadius: 0 } },
    },
    MuiToggleButton: {
      styleOverrides: {
        root: {
          borderRadius: 0,
          borderColor: RULE,
          color: INK_SOFT,
          padding: "4px 12px",
          fontSize: "0.875rem",
          lineHeight: 1.5,
          "&:hover": { color: INK, backgroundColor: "transparent" },
          "&.Mui-selected, &.Mui-selected:hover": { color: PAPER, backgroundColor: INK },
          "&.Mui-focusVisible": { outline: `2px solid ${SIGNAL}`, outlineOffset: 1 },
        },
      },
    },
    MuiIconButton: {
      styleOverrides: {
        root: {
          borderRadius: 0,
          color: INK,
          border: `1px solid ${RULE}`,
          padding: 5,
          "&:hover": { borderColor: INK, backgroundColor: "transparent" },
          "&.Mui-focusVisible": { outline: `2px solid ${SIGNAL}`, outlineOffset: 1 },
        },
      },
    },
    MuiOutlinedInput: {
      styleOverrides: {
        root: {
          borderRadius: 0,
          fontSize: "0.875rem",
          "& .MuiOutlinedInput-notchedOutline": { borderColor: RULE },
          "&:hover .MuiOutlinedInput-notchedOutline": { borderColor: INK },
          "&.Mui-focused .MuiOutlinedInput-notchedOutline": { borderColor: SIGNAL, borderWidth: 1 },
        },
      },
    },
    MuiPaper: {
      styleOverrides: { root: { backgroundImage: "none" } },
    },
    MuiDialog: {
      styleOverrides: {
        paper: { borderRadius: 0, border: `1px solid ${RULE}`, boxShadow: "0 12px 40px rgba(15,28,35,0.22)" },
      },
    },
    MuiDialogTitle: {
      styleOverrides: {
        root: { fontFamily: "Newsreader, Georgia, serif", fontWeight: 400, fontSize: "1.75rem", paddingBottom: 4 },
      },
    },
    MuiTooltip: {
      styleOverrides: {
        tooltip: {
          backgroundColor: "#ffffff",
          color: INK,
          fontSize: "0.8125rem",
          borderRadius: 2,
          boxShadow: "0 2px 10px rgba(15, 28, 35, 0.18)",
          padding: "7px 10px",
        },
        arrow: { color: "#ffffff" },
      },
    },
    MuiPickersDay: {
      styleOverrides: {
        root: {
          "&.Mui-selected, &.Mui-selected:hover, &.Mui-selected:focus": { backgroundColor: INK },
        },
      },
    },
    MuiPopover: {
      styleOverrides: { paper: { borderRadius: 0, border: `1px solid ${RULE}` } },
    },
  },
});
