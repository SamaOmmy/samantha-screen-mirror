import { useEffect, useState } from "react";

interface InstallPromptEvent extends Event {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
}

/** Install-as-app support: Chrome/Android gives us a prompt; iPhone needs manual steps. */
export function useInstall() {
  const [event, setEvent] = useState<InstallPromptEvent | null>(null);
  const standalone =
    window.matchMedia("(display-mode: standalone)").matches || (navigator as any).standalone === true;
  const ios = /iphone|ipad|ipod/i.test(navigator.userAgent);

  useEffect(() => {
    const onPrompt = (e: Event) => { e.preventDefault(); setEvent(e as InstallPromptEvent); };
    const onInstalled = () => setEvent(null);
    window.addEventListener("beforeinstallprompt", onPrompt);
    window.addEventListener("appinstalled", onInstalled);
    return () => {
      window.removeEventListener("beforeinstallprompt", onPrompt);
      window.removeEventListener("appinstalled", onInstalled);
    };
  }, []);

  return {
    installed: standalone,
    canPrompt: !!event,
    ios,
    secure: window.isSecureContext,
    install: async () => { await event?.prompt(); setEvent(null); },
  };
}
