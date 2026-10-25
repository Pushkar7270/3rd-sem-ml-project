import { Component, useCallback, useEffect, useMemo, useState } from "react";
import {
  Activity,
  BarChart3,
  Code2,
  FileText,
  History,
  Inbox,
  LayoutDashboard,
  Menu,
  Plus,
  RefreshCw,
  Sparkles,
  Users,
} from "lucide-react";
import { api } from "./api";
import { PAGE_META, fmtInt } from "./lib/format";
import { ToastContext } from "./lib/toast";
import { EmptyState } from "./components/ui";
import Overview from "./pages/Overview";
import Customers from "./pages/Customers";
import Predict from "./pages/Predict";
import Insights from "./pages/Insights";
import Queue from "./pages/Queue";
import HistoryPage from "./pages/History";
import CustomerDrawer from "./components/CustomerDrawer";

const NAV = [
  { id: "overview", label: "Overview", icon: LayoutDashboard },
  { id: "customers", label: "Customers", icon: Users },
  { id: "predict", label: "Score customer", icon: Sparkles },
  { id: "insights", label: "Model insights", icon: BarChart3 },
  { id: "queue", label: "Retention queue", icon: Inbox },
  { id: "history", label: "Score history", icon: History },
];

function routeFromHash() {
  const route = (window.location.hash.replace(/^#\/?/, "") || "overview").split("?")[0];
  return PAGE_META[route] ? route : "overview";
}

function useHashRoute() {
  const [route, setRoute] = useState(routeFromHash);
  useEffect(() => {
    const handler = () => setRoute(routeFromHash());
    window.addEventListener("hashchange", handler);
    return () => window.removeEventListener("hashchange", handler);
  }, []);
  useEffect(() => {
    window.scrollTo({ top: 0, behavior: "instant" });
  }, [route]);
  return route;
}

export default function App() {
  const route = useHashRoute();
  const [core, setCore] = useState({ summary: null, info: null, metrics: null, eda: null });
  const [status, setStatus] = useState("loading");
  const [error, setError] = useState("");
  const [refreshToken, setRefreshToken] = useState(0);
  const [mobileNav, setMobileNav] = useState(false);
  const [drawerCustomer, setDrawerCustomer] = useState(null);
  const [toasts, setToasts] = useState([]);

  const toast = useCallback((message, type = "success") => {
    const id = `${Date.now()}-${Math.random()}`;
    setToasts((items) => [...items, { id, message, type }]);
    window.setTimeout(() => {
      setToasts((items) => items.filter((item) => item.id !== id));
    }, 3600);
  }, []);

  const loadCore = useCallback(async () => {
    const [summary, info, metrics] = await Promise.all([
      api("/dashboard/summary"),
      api("/model/info"),
      api("/model/metrics"),
    ]);
    const eda = await api("/eda/summary").catch(() => null);
    setCore({ summary, info, metrics, eda });
    return { summary, info, metrics, eda };
  }, []);

  useEffect(() => {
    let active = true;
    loadCore()
      .then(() => {
        if (active) setStatus("ready");
      })
      .catch((err) => {
        if (!active) return;
        setError(err.message);
        setStatus("error");
      });
    return () => {
      active = false;
    };
  }, [loadCore]);

  useEffect(() => {
    if (!window.location.hash) window.history.replaceState(null, "", "#/overview");
  }, []);

  const refresh = useCallback(async () => {
    try {
      await loadCore();
      setRefreshToken((token) => token + 1);
      toast("Dashboard refreshed");
    } catch (err) {
      toast(err.message, "error");
    }
  }, [loadCore, toast]);

  const go = useCallback((id) => {
    window.location.hash = `#/${id}`;
    setMobileNav(false);
  }, []);

  useEffect(() => {
    const handler = (event) => {
      if (event.key === "Escape") {
        setDrawerCustomer(null);
        setMobileNav(false);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  const page = useMemo(() => {
    const props = {
      core,
      refreshCore: loadCore,
      toast,
      openCustomer: setDrawerCustomer,
      go,
    };
    switch (route) {
      case "customers":
        return <Customers {...props} />;
      case "predict":
        return <Predict {...props} />;
      case "insights":
        return <Insights {...props} />;
      case "queue":
        return <Queue {...props} />;
      case "history":
        return <HistoryPage {...props} />;
      default:
        return <Overview {...props} />;
    }
  }, [route, core, loadCore, toast, go, refreshToken]);

  const summary = core.summary;
  const pending = summary?.actions?.pending || 0;

  return (
    <ToastContext.Provider value={toast}>
      <div className="ambient ambient-a" />
      <div className="ambient ambient-b" />
      <div className="ambient ambient-c" />
      <div className="ambient ambient-d" />
      <div className="dot-field" aria-hidden="true" />

      <div className="app-shell">
        <aside className={`sidebar ${mobileNav ? "open" : ""}`}>
          <a className="brand" href="#/overview" aria-label="RetainIQ home">
            <span className="brand-mark">
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <path d="M5 17V7h6.1c4 0 6.2 2.2 6.2 5s-2.2 5-6.2 5H5Zm4-3.4h2c1.6 0 2.5-.7 2.5-1.6S12.6 10.4 11 10.4H9v3.2Z" />
              </svg>
            </span>
            <span className="brand-copy">
              <strong>
                Retain<span>IQ</span>
              </strong>
              <small>churn intelligence</small>
            </span>
          </a>

          <p className="nav-label">Workspace</p>
          <nav className="nav" aria-label="Primary">
            {NAV.map((item) => {
              const Icon = item.icon;
              return (
                <a
                  key={item.id}
                  href={`#/${item.id}`}
                  className={route === item.id ? "active" : ""}
                  onClick={() => setMobileNav(false)}
                >
                  <span className="nav-icon">
                    <Icon />
                  </span>
                  <span>{item.label}</span>
                  {item.id === "queue" && pending > 0 ? (
                    <span className="nav-badge">{fmtInt(pending)}</span>
                  ) : null}
                </a>
              );
            })}
          </nav>

          <div className="sidebar-foot">
            <div className={`status-chip ${status === "error" ? "offline" : ""}`}>
              <span className="status-dot" />
              <div>
                <strong>{status === "error" ? "API offline" : "Model online"}</strong>
                <small>
                  {summary ? `${summary.model.name} · ${summary.model.version}` : "connecting…"}
                </small>
              </div>
            </div>
            <a className="side-link" href="/docs" target="_blank" rel="noreferrer">
              <Code2 size={15} /> API documentation
            </a>
            <a className="side-link" href="/model/card" target="_blank" rel="noreferrer">
              <FileText size={15} /> Model card
            </a>
            <p className="sidebar-note">React + Vite · SQLite · No sign-in</p>
          </div>
        </aside>

        <div className="workspace">
          <header className="topbar">
            <div className="topbar-left">
              <button
                className="icon-btn mobile-menu"
                aria-label="Toggle navigation"
                onClick={() => setMobileNav((open) => !open)}
              >
                <Menu size={18} />
              </button>
              <div className="crumb">
                <span className="crumb-root">RetainIQ</span>
                <span className="crumb-sep">/</span>
                <span>{PAGE_META[route].title}</span>
              </div>
            </div>
            <div className="topbar-actions">
              <span className="as-of">
                Updated{" "}
                {new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
              </span>
              <button className="btn ghost small" onClick={refresh}>
                <RefreshCw size={15} /> Refresh
              </button>
              <a className="btn primary small" href="#/predict">
                <Plus size={15} /> Score customer
              </a>
              <div className="avatar" title="Demo workspace">
                P
              </div>
            </div>
          </header>

          <main className="main" aria-live="polite">
            {status === "loading" ? (
              <div className="loading-screen">
                <div className="loader-ring" />
                <p>Connecting to the churn model…</p>
              </div>
            ) : status === "error" ? (
              <div className="fatal">
                <p className="eyebrow">Backend unavailable</p>
                <h1>Could not connect to the churn model</h1>
                <p>{error}</p>
                <p>Start the API and make sure a trained model exists:</p>
                <code>uv run churn-train &amp;&amp; uv run churn-serve</code>
                <p style={{ marginTop: 18 }}>
                  Then open <b>/app/</b> again.
                </p>
              </div>
            ) : (
              <PageErrorBoundary key={`${route}-${refreshToken}`}>{page}</PageErrorBoundary>
            )}
          </main>
        </div>
      </div>

      <CustomerDrawer
        customerId={drawerCustomer}
        onClose={() => setDrawerCustomer(null)}
        toast={toast}
        onSaved={loadCore}
      />

      <div className="toast-stack" aria-live="polite">
        {toasts.map((item) => (
          <div className={`toast ${item.type}`} key={item.id}>
            <span className="toast-dot" />
            <span>{item.message}</span>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

class PageErrorBoundary extends Component {
  state = { error: null };
  static getDerivedStateFromError(error) {
    return { error };
  }
  render() {
    if (this.state.error) {
      return (
        <div className="card">
          <EmptyState
            icon={<Activity size={24} />}
            title="Could not render this page"
            text={this.state.error.message}
          />
        </div>
      );
    }
    return this.props.children;
  }
}
