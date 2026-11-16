import { useCallback, useEffect, useState } from "react";

import SignalField from "./SignalField.jsx";
import { connectUrl, fetchAccount, signOut } from "./api.js";
import Dashboard from "./dashboard/Dashboard.jsx";

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

  const recording = state === RECORDING && account;

  return (
    <main className={recording ? "page wide" : "page"}>
      <header className="masthead">
        <span className="wordmark">health·cloud</span>
        {recording ? (
          <AccountStrip account={account} onConnect={connect} onSignOut={disconnect} />
        ) : (
          <span className="state">{describeState(state, account)}</span>
        )}
      </header>

      {!recording && <SignalField recording={false} />}

      {state === LOADING && <Panel title="Checking the recorder." />}

      {state === UNREACHABLE && (
        <Panel title="The recorder isn't answering.">
          <p>
            Nothing is listening on localhost:8000. Start it with{" "}
            <code>uv run uvicorn server.main:app --workers 3</code>, then reload
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

      {recording && <Dashboard />}
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

// The account, reduced to one line above the dashboard: who is signed in, how
// long until Google needs consent again, and the two things to do about it.
function AccountStrip({ account, onConnect, onSignOut }) {
  const days = account.days_until_reconsent;
  const expiring = account.needs_reconsent || days < 2;

  return (
    <div className="account">
      <span className="account-who">{account.email ?? account.health_user_id}</span>
      <span className={expiring ? "expiring" : undefined}>
        {account.needs_reconsent ? (
          "Recording stopped"
        ) : (
          <>
            Connection expires in <span className="figure">{Math.max(days, 0).toFixed(1)}</span> days
          </>
        )}
      </span>
      <span className="account-scopes">
        <span className="figure">{healthScopeCount(account)}</span> read-only permissions
      </span>
      <button type="button" className="link" onClick={onConnect}>
        {account.needs_reconsent ? "Reconnect" : "Renew"}
      </button>
      <button type="button" className="link" onClick={onSignOut}>
        Sign out
      </button>
    </div>
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
