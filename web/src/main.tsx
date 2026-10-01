import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "./styles.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>
);

// Service workers need a secure context (HTTPS or localhost). Over plain-HTTP Tailscale
// IPs the app still works, it just isn't cached for offline start.
if ("serviceWorker" in navigator && window.isSecureContext) {
  // When an update of the PC's app installs a new service worker, reload once so the phone
  // runs the new version straight away instead of the cached old one.
  const hadController = !!navigator.serviceWorker.controller;
  let reloaded = false;
  navigator.serviceWorker.addEventListener("controllerchange", () => {
    if (hadController && !reloaded) { reloaded = true; location.reload(); }
  });
  navigator.serviceWorker.register("/sw.js").catch(() => {});
}
