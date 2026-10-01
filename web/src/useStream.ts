import { useCallback, useEffect, useRef, useState } from "react";
import { api, ServerDown, Unauthorized, type ServerState } from "./api";

/** Why the PC cannot be used: "network" = not reachable at all, "server" = reachable but the app is not running. */
export type Unreachable = "network" | "server" | null;

export type Status = "connecting" | "live" | "retrying" | "capture-error";

const POLL_MS = 1500;
const MAX_BACKOFF = 8000;

/** Owns the MJPEG connection: reconnects on errors, stalls, wake-up and network changes. */
export function useStream(onUnauthorized: () => void) {
  const [src, setSrc] = useState("");
  const [status, setStatus] = useState<Status>("connecting");
  const [server, setServer] = useState<ServerState | null>(null);
  const [fps, setFps] = useState(0);
  const [unreachable, setUnreachable] = useState<Unreachable>(null);

  const backoff = useRef(500);
  const retryTimer = useRef<number>(0);
  const last = useRef({ tick: -1, seq: -1, at: 0, stalled: 0 });
  const unauthorized = useRef(onUnauthorized);
  unauthorized.current = onUnauthorized;

  const connect = useCallback(() => {
    clearTimeout(retryTimer.current);
    last.current = { tick: -1, seq: -1, at: 0, stalled: 0 };
    setStatus("connecting");
    setSrc(`/stream?t=${Date.now()}`);
  }, []);

  const retry = useCallback(() => {
    setStatus("retrying");
    clearTimeout(retryTimer.current);
    retryTimer.current = window.setTimeout(connect, backoff.current);
    backoff.current = Math.min(backoff.current * 2, MAX_BACKOFF);
  }, [connect]);

  // The first frame arrived.
  const onLoad = useCallback(() => {
    backoff.current = 500;
    setStatus((cur) => (cur === "capture-error" ? cur : "live"));
  }, []);

  useEffect(() => {
    connect();
    let stopped = false;

    const poll = async () => {
      try {
        const s = await api.state();
        if (stopped) return;
        setUnreachable(null);
        setServer(s);
        const l = last.current;
        const now = performance.now();
        if (l.at && s.seq !== l.seq) setFps(Math.round(((s.seq - l.seq) * 1000) / (now - l.at)));
        else if (l.at) setFps(0);
        if (s.error) {
          setStatus("capture-error");
        } else if (s.tick !== l.tick) {
          l.stalled = 0;
          setStatus((cur) => (cur === "capture-error" ? "live" : cur));
        } else if (++l.stalled >= 2) {
          retry(); // the capture counter stopped moving: the stream is stuck
        }
        l.tick = s.tick; l.seq = s.seq; l.at = now;
      } catch (e) {
        if (e instanceof Unauthorized) unauthorized.current();
        else if (!stopped) { setUnreachable(e instanceof ServerDown ? "server" : "network"); retry(); }
      }
    };

    const timer = window.setInterval(poll, POLL_MS);
    const wake = () => { if (!document.hidden) connect(); };
    document.addEventListener("visibilitychange", wake);
    window.addEventListener("online", connect);
    return () => {
      stopped = true;
      clearInterval(timer);
      clearTimeout(retryTimer.current);
      document.removeEventListener("visibilitychange", wake);
      window.removeEventListener("online", connect);
    };
  }, [connect, retry]);

  return { src, status, server, fps, unreachable, onLoad, onError: retry, reconnect: connect };
}
