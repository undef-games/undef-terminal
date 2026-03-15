import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import { readBootstrap } from "./bootstrap";
import "./styles/tokens.css";

const rootEl = document.getElementById("app-root");
if (!rootEl) throw new Error("Missing #app-root");

const bootstrap = readBootstrap();

createRoot(rootEl).render(
  <StrictMode>
    <App bootstrap={bootstrap} />
  </StrictMode>,
);
