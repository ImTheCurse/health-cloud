import { ThemeProvider } from "@mui/material/styles";
import { AdapterDayjs } from "@mui/x-date-pickers/AdapterDayjs";
import { LocalizationProvider } from "@mui/x-date-pickers/LocalizationProvider";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import App from "./App.jsx";
import { muiTheme } from "./dashboard/muiTheme.js";
import "./styles.css";

createRoot(document.getElementById("root")).render(
  <StrictMode>
    <ThemeProvider theme={muiTheme}>
      <LocalizationProvider dateAdapter={AdapterDayjs}>
        <App />
      </LocalizationProvider>
    </ThemeProvider>
  </StrictMode>,
);
