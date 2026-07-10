import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import App from "./App";
import { PrivacyNoticePage } from "./components/PrivacyNoticePage";
import "./index.css";

const queryClient = new QueryClient();

function Root() {
  const path = window.location.pathname.replace(/\/$/, "") || "/";
  if (path === "/privacy") {
    return <PrivacyNoticePage />;
  }
  return <App />;
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <Root />
    </QueryClientProvider>
  </StrictMode>,
);
