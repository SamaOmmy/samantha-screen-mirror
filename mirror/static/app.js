(() => {
  const img = document.getElementById("screen");
  const dot = document.getElementById("dot");
  const msg = document.getElementById("msg");
  const fsBtn = document.getElementById("fs");

  const POLL_MS = 2000;
  let lastSeq = -1;
  let stalledPolls = 0;
  let retryDelay = 500;
  let retryTimer = null;

  function setState(ok, text) {
    dot.className = ok ? "" : "off";
    msg.textContent = text;
  }

  // (Re)open the MJPEG stream. The query value only defeats the browser cache.
  function connect() {
    clearTimeout(retryTimer);
    lastSeq = -1;
    stalledPolls = 0;
    setState(false, "Connecting…");
    img.src = "/stream?t=" + Date.now();
  }

  function scheduleReconnect() {
    setState(false, "Disconnected, retrying…");
    clearTimeout(retryTimer);
    retryTimer = setTimeout(connect, retryDelay);
    retryDelay = Math.min(retryDelay * 2, 8000);
  }

  img.addEventListener("load", () => { retryDelay = 500; });
  img.addEventListener("error", scheduleReconnect);

  // The server's frame counter must keep advancing; if not, the stream is stuck.
  async function poll() {
    try {
      const r = await fetch("/status", { cache: "no-store", credentials: "same-origin" });
      if (r.status === 401) { setState(false, "Unauthorized — reopen the link with ?token="); return; }
      if (!r.ok) throw new Error(r.status);
      const s = await r.json();
      if (s.seq !== lastSeq) {
        lastSeq = s.seq;
        stalledPolls = 0;
        setState(true, "Live");
      } else if (++stalledPolls >= 2) {
        scheduleReconnect();
      }
    } catch (e) {
      scheduleReconnect();
    }
  }
  setInterval(poll, POLL_MS);

  // Reconnect when the phone wakes the tab or the network comes back.
  document.addEventListener("visibilitychange", () => { if (!document.hidden) connect(); });
  window.addEventListener("online", connect);

  // Fullscreen: real API where supported (not on iPhone Safari), CSS fallback otherwise.
  function isFull() { return !!(document.fullscreenElement || document.webkitFullscreenElement); }
  function setImmersive(on) { document.body.classList.toggle("immersive", on); }

  fsBtn.addEventListener("click", async () => {
    const el = document.documentElement;
    const req = el.requestFullscreen || el.webkitRequestFullscreen;
    if (isFull()) {
      (document.exitFullscreen || document.webkitExitFullscreen).call(document);
    } else if (req) {
      try { await req.call(el); } catch (e) { setImmersive(true); }
    } else {
      setImmersive(!document.body.classList.contains("immersive"));
    }
  });
  document.addEventListener("fullscreenchange", () => setImmersive(isFull()));
  document.addEventListener("webkitfullscreenchange", () => setImmersive(isFull()));

  // In immersive mode, tapping the screen toggles the control bar.
  document.getElementById("stage").addEventListener("click", () => {
    if (document.body.classList.contains("immersive")) document.body.classList.toggle("show-bar");
  });

  connect();
})();
