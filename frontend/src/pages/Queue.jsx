import { useCallback, useEffect, useState } from "react";
import { Check, Inbox, Users, X, Activity } from "lucide-react";
import { EmptyState, RiskBadge, PageHead } from "../components/ui";
import { api } from "../api";
import { fmtDate, fmtInt, fmtPct } from "../lib/format";

const STATUSES = ["pending", "contacted", "accepted", "declined"];

const STATUS_META = {
  pending: { icon: Inbox, color: "var(--amber)" },
  contacted: { icon: Activity, color: "var(--blue)" },
  accepted: { icon: Check, color: "var(--green)" },
  declined: { icon: X, color: "var(--red)" },
};

export default function Queue({ openCustomer, toast, refreshCore }) {
  const [actions, setActions] = useState([]);
  const [summary, setSummary] = useState({});
  const [filter, setFilter] = useState("all");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [list, counts] = await Promise.all([api("/actions?limit=500"), api("/actions/summary")]);
      setActions(list.actions || []);
      setSummary(counts || {});
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const updateStatus = async (action, status) => {
    try {
      await api(`/actions/${action.id}`, {
        method: "PATCH",
        body: JSON.stringify({ status }),
      });
      toast(`Action marked ${status}`);
      await load();
      if (refreshCore) await refreshCore();
    } catch (err) {
      toast(err.message, "error");
    }
  };

  const rows = filter === "all" ? actions : actions.filter((action) => action.status === filter);

  return (
    <>
      <PageHead
        eyebrow="Action workspace"
        title="Retention queue"
        sub="Actions saved from customer drill-downs. Update the workflow status as the team works each playbook."
        actions={
          <a className="btn primary small" href="#/customers">
            <Users size={15} /> Find customers
          </a>
        }
      />

      <section className="kpi-grid">
        {STATUSES.map((status) => {
          const Icon = STATUS_META[status].icon;
          const value = summary[status] || 0;
          return (
            <article className="kpi" key={status}>
              <div className="kpi-top">
                <span>{status}</span>
                <span className="kpi-icon">
                  <Icon size={15} />
                </span>
              </div>
              <div className="kpi-value">{fmtInt(value)}</div>
              <div className="kpi-foot">Saved playbook actions</div>
              <div
                className={`kpi-bar ${status === "pending" ? "amber" : status === "declined" ? "red" : ""}`}
              >
                <span style={{ width: `${Math.min(100, value * 12)}%` }} />
              </div>
            </article>
          );
        })}
      </section>

      <div className="toolbar">
        <div className="filters">
          <div className="tabs">
            <button
              className={`tab ${filter === "all" ? "active" : ""}`}
              onClick={() => setFilter("all")}
            >
              All
            </button>
            {STATUSES.map((status) => (
              <button
                className={`tab ${filter === status ? "active" : ""}`}
                key={status}
                onClick={() => setFilter(status)}
              >
                {status}
              </button>
            ))}
          </div>
        </div>
        <span className="muted">{fmtInt(rows.length)} actions</span>
      </div>

      <article className="card">
        {loading ? (
          <div className="empty-state">
            <div className="loader-ring" style={{ margin: "0 auto 14px" }} />
            <p>Loading retention actions…</p>
          </div>
        ) : error ? (
          <EmptyState title="Could not load the queue" text={error} />
        ) : rows.length ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Customer</th>
                  <th>Recommendation</th>
                  <th>Offer</th>
                  <th>Risk</th>
                  <th>Status</th>
                  <th>Updated</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {rows.map((action) => (
                  <tr key={action.id}>
                    <td>
                      <strong>{action.customer_id}</strong>
                      <span className="sub">{fmtPct(action.churn_probability, 0)} churn risk</span>
                    </td>
                    <td>
                      <strong>{action.title}</strong>
                      <span className="sub">{action.recommendation_id}</span>
                    </td>
                    <td style={{ maxWidth: 220 }}>{action.offer}</td>
                    <td>
                      <RiskBadge level={action.risk_level} />
                    </td>
                    <td>
                      <select
                        className="status-select"
                        value={action.status}
                        onChange={(event) => updateStatus(action, event.target.value)}
                        aria-label="Update status"
                      >
                        {STATUSES.map((status) => (
                          <option value={status} key={status}>
                            {status}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td>{fmtDate(action.updated_at)}</td>
                    <td>
                      <button
                        className="btn ghost tiny"
                        onClick={() => openCustomer(action.customer_id)}
                      >
                        Open
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState
            icon={<Inbox size={24} />}
            title="No actions in this view"
            text="Open a high-risk customer, review the playbook and add an action to the queue."
            action={
              <a className="btn ghost small" href="#/customers">
                Browse customers
              </a>
            }
          />
        )}
      </article>
    </>
  );
}
