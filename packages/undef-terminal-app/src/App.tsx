import type { AppBootstrap } from "./api/types";
import { ConnectPage } from "./components/connect/ConnectPage";
import { DashboardPage } from "./components/dashboard/DashboardPage";
import { OperatorPage } from "./components/operator/OperatorPage";
import { ReplayPage } from "./components/replay/ReplayPage";
import { SessionPage } from "./components/session/SessionPage";

interface AppProps {
  bootstrap: AppBootstrap;
}

export function App({ bootstrap }: AppProps) {
  switch (bootstrap.page_kind) {
    case "dashboard":
      return <DashboardPage bootstrap={bootstrap} />;
    case "connect":
      return <ConnectPage bootstrap={bootstrap} />;
    case "operator":
      return <OperatorPage bootstrap={bootstrap} />;
    case "session":
      return <SessionPage bootstrap={bootstrap} />;
    case "replay":
      return <ReplayPage bootstrap={bootstrap} />;
  }
}
