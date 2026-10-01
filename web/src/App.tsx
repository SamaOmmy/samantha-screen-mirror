import { useEffect, useState } from "react";
import { api, Unauthorized } from "./api";
import Login from "./Login";
import Viewer from "./Viewer";

type Auth = "checking" | "in" | "out";

export default function App() {
  const [auth, setAuth] = useState<Auth>("checking");

  useEffect(() => {
    api.state().then(() => setAuth("in")).catch((e) => setAuth(e instanceof Unauthorized ? "out" : "in"));
  }, []);

  if (auth === "checking") return <div className="center muted">Loading…</div>;
  if (auth === "out") return <Login onDone={() => setAuth("in")} />;
  return <Viewer onSignedOut={() => setAuth("out")} />;
}
