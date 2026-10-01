import { useState, type FormEvent } from "react";

interface Device {
  name: string;
  url: string;
}

const KEY = "sm.devices";

function load(): Device[] {
  try {
    const parsed = JSON.parse(localStorage.getItem(KEY) ?? "[]");
    return Array.isArray(parsed) ? parsed.filter((d) => d && typeof d.name === "string" && typeof d.url === "string") : [];
  } catch {
    return [];
  }
}

function save(devices: Device[]) {
  try { localStorage.setItem(KEY, JSON.stringify(devices)); } catch { /* storage blocked: list just won't persist */ }
}

/** Normalises what the user typed to an http(s) origin, or returns null. */
function parseAddress(text: string): string | null {
  const raw = text.trim();
  if (!raw) return null;
  try {
    const u = new URL(/^https?:\/\//i.test(raw) ? raw : `https://${raw}`);
    return u.protocol === "http:" || u.protocol === "https:" ? u.origin : null;
  } catch {
    return null;
  }
}

/** Bookmarks for other PCs running this app. Each PC has its own address and token. */
export default function Devices() {
  const [devices, setDevices] = useState<Device[]>(load);
  const [name, setName] = useState("");
  const [address, setAddress] = useState("");
  const [error, setError] = useState("");

  function add(e: FormEvent) {
    e.preventDefault();
    const url = parseAddress(address);
    if (!url) return setError("Enter the PC's address, like https://my-pc.tail1234.ts.net");
    const next = [...devices.filter((d) => d.url !== url), { name: name.trim() || new URL(url).hostname, url }];
    setDevices(next);
    save(next);
    setName(""); setAddress(""); setError("");
  }

  function remove(url: string) {
    const next = devices.filter((d) => d.url !== url);
    setDevices(next);
    save(next);
  }

  return (
    <div className="help">
      <h3>My PCs</h3>
      <ul className="devices">
        <li>
          <span className="grow">{location.hostname} <span className="muted">(this PC)</span></span>
        </li>
        {devices.filter((d) => d.url !== location.origin).map((d) => (
          <li key={d.url}>
            <span className="grow">{d.name}<br /><span className="muted small">{new URL(d.url).host}</span></span>
            <a className="btn" href={d.url}>Open</a>
            <button onClick={() => remove(d.url)} aria-label={`Remove ${d.name}`}>✕</button>
          </li>
        ))}
      </ul>
      <form className="add-device" onSubmit={add}>
        <input placeholder="Name (optional)" value={name} onChange={(e) => setName(e.target.value)} />
        <input placeholder="Address, e.g. https://other-pc.tail1234.ts.net" value={address}
          onChange={(e) => setAddress(e.target.value)} inputMode="url" autoCapitalize="off" />
        {error && <p className="error" role="alert">{error}</p>}
        <button type="submit" disabled={!address.trim()}>Add PC</button>
      </form>
      <p className="muted small">
        Each PC needs the app set up on it and its own sign-in the first time (run <code>samantha-mirror link</code> there).
      </p>
    </div>
  );
}
