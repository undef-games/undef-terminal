function initTerminalPage(): void {
  const container = document.getElementById("app");
  if (!(container instanceof HTMLElement)) {
    throw new Error("Missing #app container");
  }
  const TerminalWidget = window.UndefTerminal;
  if (typeof TerminalWidget !== "function") {
    throw new Error("UndefTerminal is not available");
  }
  window.demoTerminal = new TerminalWidget(container);
}

initTerminalPage();
