import { useEffect } from "react";

/** Keeps the phone screen on while watching (where the browser supports it). */
export function useWakeLock(active: boolean) {
  useEffect(() => {
    if (!active || !("wakeLock" in navigator)) return;
    let lock: WakeLockSentinel | null = null;
    let cancelled = false;
    const acquire = async () => {
      try {
        const l = await navigator.wakeLock.request("screen");
        if (cancelled) l.release(); else lock = l;
      } catch { /* not allowed right now (e.g. low battery); ignore */ }
    };
    acquire();
    // The lock is dropped when the tab is hidden, so take it again on return.
    const onVisible = () => { if (!document.hidden) acquire(); };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      cancelled = true;
      document.removeEventListener("visibilitychange", onVisible);
      lock?.release();
    };
  }, [active]);
}
