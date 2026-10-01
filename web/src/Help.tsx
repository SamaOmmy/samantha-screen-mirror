import { useInstall } from "./useInstall";

const PLAY = "https://play.google.com/store/apps/details?id=com.tailscale.ipn";
const APPLE = "https://apps.apple.com/app/tailscale/id1470499037";

/** Plain-language setup and install help, used on the login screen and in settings. */
export default function Help({ compact = false }: { compact?: boolean }) {
  const inst = useInstall();
  return (
    <div className="help">
      {!compact && (
        <>
          <h3>First time here?</h3>
          <ol>
            <li>On your PC, run <code>samantha-mirror link</code>. It shows a QR code: scan it and you are signed in.</li>
            <li>
              This phone needs the free <strong>Tailscale</strong> app, signed in to the same account as the PC and switched on:{" "}
              <a href={PLAY} target="_blank" rel="noreferrer">Android</a> · <a href={APPLE} target="_blank" rel="noreferrer">iPhone</a>
            </li>
          </ol>
        </>
      )}
      <h3>Install as an app</h3>
      {inst.installed ? (
        <p className="muted">You are using the installed app.</p>
      ) : inst.canPrompt ? (
        <button className="primary" onClick={inst.install}>Install app</button>
      ) : inst.ios ? (
        <p className="muted">Tap the Share button in Safari, then <strong>Add to Home Screen</strong>.</p>
      ) : !inst.secure ? (
        <p className="muted">
          Your browser only offers a full install over HTTPS. Open this app through your PC's
          <code> https://…ts.net </code> address (run <code>samantha-mirror setup</code> on the PC to set it up).
          You can still use the browser menu → <strong>Add to Home screen</strong>.
        </p>
      ) : (
        <p className="muted">Use the browser menu → <strong>Install app</strong> or <strong>Add to Home screen</strong>.</p>
      )}
    </div>
  );
}
