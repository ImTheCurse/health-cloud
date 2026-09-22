import { useCallback, useEffect, useState } from "react";

import SignalField from "./SignalField.jsx";
import { connectUrl, fetchAccount, signOut } from "./api.js";

const LOADING = "loading";
const DISCONNECTED = "disconnected";
const RECORDING = "recording";
const UNREACHABLE = "unreachable";

export default function App() {
  const [state, setState] = useState(LOADING);
  const [account, setAccount] = useState(null);

  const load = useCallback(async () => {
    try {
      const result = await fetchAccount();
      setAccount(result);
      setState(result ? RECORDING : DISCONNECTED);
    } catch {
      setState(UNREACHABLE);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const connect = () => window.location.assign(connectUrl);

  const disconnect = async () => {
    await signOut();
    setAccount(null);
    setState(DISCONNECTED);
  };

  return (
    <main className="page">
      <header className="masthead">
        <span className="wordmark">health·cloud</span>
        <span className="state">{describeState(state, account)}</span>
      </header>

      <SignalField recording={state === RECORDING} />

      {state === LOADING && <Panel title="Checking the recorder." />}

      {state === UNREACHABLE && (
        <Panel title="The recorder isn't answering.">
          <p>
            Nothing is listening on localhost:8000. Start it with{" "}
            <code>uv run uvicorn server.main:app --reload</code>, then reload
            this page.
          </p>
        </Panel>
      )}

      {state === DISCONNECTED && (
        <Panel title="Nothing recorded yet.">
          <p>
            This server holds no measurements. Connect Google Health and your
            steps, sleep and heart rate begin recording here, on hardware you
            own.
          </p>
          <p className="aside">
            Google will warn you that this app is unverified. It is — it is
            yours, and it reads your data without writing anything back.
          </p>
          <button type="button" className="action" onClick={connect}>
            Connect Google Health
          </button>
        </Panel>
      )}

      {state === RECORDING && account && (
        <Panel title={account.needs_reconsent ? "Recording stopped." : "Recording."}>
          <Readout account={account} />
          <div className="actions">
            <button type="button" className="action" onClick={connect}>
              {account.needs_reconsent ? "Reconnect Google Health" : "Renew connection"}
            </button>
            <button type="button" className="action quiet" onClick={disconnect}>
              Sign out
            </button>
          </div>
        </Panel>
      )}
    </main>
  );
}

function Panel({ title, children }) {
  return (
    <section className="panel">
      <h1>{title}</h1>
      {children}
    </section>
  );
}

function Readout({ account }) {
  const days = account.days_until_reconsent;
  const expiring = account.needs_reconsent || days < 2;

  return (
    <dl className="readout">
      <div>
        <dt>Account</dt>
        <dd>{account.email ?? account.health_user_id}</dd>
      </div>
      <div>
        <dt>Health permissions</dt>
        <dd>
          <span className="figure">{healthScopeCount(account)}</span> read-only
        </dd>
      </div>
      <div>
        <dt>Connection expires</dt>
        <dd className={expiring ? "expiring" : undefined}>
          <span className="figure">{Math.max(days, 0).toFixed(1)}</span> days from now
        </dd>
      </div>
    </dl>
  );
}

// Google grants openid, email and profile alongside the health scopes, so the
// raw list is longer than the data access actually granted.
function healthScopeCount(account) {
  return account.granted_scopes.filter((scope) => scope.includes("googlehealth"))
    .length;
}

function describeState(state, account) {
  if (state === LOADING) return "checking";
  if (state === UNREACHABLE) return "offline";
  if (state === DISCONNECTED) return "not connected";
  return account?.needs_reconsent ? "needs reconnecting" : "connected";
}
