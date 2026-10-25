import { useCallback, useEffect, useState } from "react";
import { Activity, Code2, Database, History, ShieldCheck, Target } from "lucide-react";
import { CardHead, EmptyState, PageHead, RiskBadge } from "../components/ui";
import { api } from "../api";
import { fmtDate, fmtInt, fmtPct } from "../lib/format";

export default function HistoryPage({ toast }) {
  const [items, setItems] = useState([]);
  const [stats, setStats] = useState(null);
  const [db, setDb] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [history, historyStats, dbStatus] = await Promise.all([
        api("/history?limit=60"),
        api("/history/stats"),
        api("/db/status"),
      ]);
      setItems(history.items || []);
      setStats(historyStats);
      setDb(dbStatus);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const recordFeedback = async (predictionId, actualChurn) => {
    try {
      await api("/feedback", {
        method: "POST",
        body: JSON.stringify({ prediction_id: predictionId, actual_churn: actualChurn }),
      });
      toast("Outcome recorded");
      await load();
    } catch (err) {
      toast(err.message, "error");
    }
  };

  return (
    <>
      <PageHead
        eyebrow="Operational audit trail"
        title="Score history"
        sub="Every score served by the API is written to SQLite. Record the observed outcome to close the feedback loop."
        actions={
          <a className="btn ghost small" href="/docs#/history" target="_blank" rel="noreferrer">
            <Code2 size={15} /> API reference
          </a>
        }
      />

      {loading ? (
        <div className="card">
          <div className="empty-state">
            <div className="loader-ring" style={{ margin: "0 auto 14px" }} />
            <p>Loading operational database…</p>
          </div>
        </div>
      ) : error ? (
        <div className="card">
          <EmptyState title="Could not load the audit trail" text={error} />
        </div>
      ) : (
        <>
          <section className="kpi-grid">
            <article className="kpi">
              <div className="kpi-top">
                <span>Total predictions</span>
                <span className="kpi-icon">
                  <Activity size={15} />
                </span>
              </div>
              <div className="kpi-value">{fmtInt(stats?.total_predictions)}</div>
              <div className="kpi-foot">
                <b>{fmtInt(stats?.last_24h)}</b> in the last 24 hours
              </div>
              <div className="kpi-bar">
                <span style={{ width: `${Math.min(100, (stats?.total_predictions || 0) * 2)}%` }} />
              </div>
            </article>
            <article className="kpi">
              <div className="kpi-top">
                <span>Predicted churners</span>
                <span className="kpi-icon">
                  <Target size={15} />
                </span>
              </div>
              <div className="kpi-value">{fmtInt(stats?.predicted_churners)}</div>
              <div className="kpi-foot">Across all logged scores</div>
              <div className="kpi-bar amber">
                <span
                  style={{ width: `${Math.min(100, (stats?.predicted_churners || 0) * 2)}%` }}
                />
              </div>
            </article>
            <article className="kpi">
              <div className="kpi-top">
                <span>Observed churn rate</span>
                <span className="kpi-icon">
                  <ShieldCheck size={15} />
                </span>
              </div>
              <div className="kpi-value">{fmtPct(stats?.observed_churn_rate)}</div>
              <div className="kpi-foot">{fmtInt(stats?.feedback_count)} outcomes recorded</div>
              <div className="kpi-bar">
                <span style={{ width: `${(stats?.observed_churn_rate || 0) * 100}%` }} />
              </div>
            </article>
            <article className="kpi">
              <div className="kpi-top">
                <span>Database</span>
                <span className="kpi-icon">
                  <Database size={15} />
                </span>
              </div>
              <div className="kpi-value">{db?.engine || "SQLite"}</div>
              <div className="kpi-foot">
                {fmtInt(db?.tables?.predictions || 0)} predictions ·{" "}
                {fmtInt(db?.tables?.feedback || 0)} feedback
              </div>
              <div className="kpi-bar">
                <span style={{ width: "100%" }} />
              </div>
            </article>
          </section>

          <article className="card">
            <CardHead
              title="Recent scores"
              sub="Newest first · payload retained in the audit database"
              action={<span className="pill">{db?.journal_mode || "WAL"} journal · no sign-in</span>}
            />
            {items.length ? (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>When</th>
                      <th>Customer</th>
                      <th>Risk</th>
                      <th>Probability</th>
                      <th>Top driver</th>
                      <th>Outcome</th>
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    {items.map((item) => (
                      <tr key={item.id}>
                        <td>{fmtDate(item.created_at)}</td>
                        <td>
                          <strong>{item.customer_id || "Ad-hoc"}</strong>
                          <span className="sub">
                            {item.model_name} {item.model_version}
                          </span>
                        </td>
                        <td>
                          <RiskBadge level={item.risk_level} />
                        </td>
                        <td>{fmtPct(item.churn_probability)}</td>
                        <td>{item.top_driver || <span className="muted">—</span>}</td>
                        <td>
                          {item.actual_churn === null || item.actual_churn === undefined ? (
                            <span className="muted">Awaiting feedback</span>
                          ) : item.actual_churn ? (
                            <span className="badge high">Churned</span>
                          ) : (
                            <span className="badge low">Retained</span>
                          )}
                        </td>
                        <td style={{ whiteSpace: "nowrap" }}>
                          {item.actual_churn === null || item.actual_churn === undefined ? (
                            <>
                              <button
                                className="btn ghost tiny"
                                onClick={() => recordFeedback(item.id, true)}
                              >
                                Churned
                              </button>{" "}
                              <button
                                className="btn ghost tiny"
                                onClick={() => recordFeedback(item.id, false)}
                              >
                                Retained
                              </button>
                            </>
                          ) : null}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <EmptyState
                icon={<History size={24} />}
                title="No predictions logged yet"
                text="Every score from the Predict page or customer drawer is recorded here automatically. Score a customer to start the audit trail."
                action={
                  <a className="btn primary small" href="#/predict">
                    Score a customer
                  </a>
                }
              />
            )}
          </article>

          <div className="grid" style={{ marginTop: 16 }}>
            <article className="card span-7">
              <CardHead title="Database status" sub="Embedded SQLite · ACID · local file" />
              <div className="segment-list">
                <div className="segment-row">
                  <span>File</span>
                  <div className="segment-track">
                    <i style={{ width: "100%" }} />
                  </div>
                  <strong
                    className="mono"
                    style={{ fontSize: 9, maxWidth: 220, overflow: "hidden", textOverflow: "ellipsis" }}
                  >
                    {db?.path}
                  </strong>
                </div>
                <div className="segment-row">
                  <span>Size</span>
                  <div className="segment-track">
                    <i style={{ width: `${Math.min(100, (db?.size_bytes || 0) / 5000)}%` }} />
                  </div>
                  <strong>{fmtInt(db?.size_bytes)} B</strong>
                </div>
                <div className="segment-row">
                  <span>Tables</span>
                  <div className="segment-track">
                    <i style={{ width: "100%" }} />
                  </div>
                  <strong>{Object.keys(db?.tables || {}).join(", ")}</strong>
                </div>
              </div>
            </article>
            <article className="card span-5">
              <CardHead title="Why close the loop?" sub="Feedback makes the next model better" />
              <p className="card-sub" style={{ fontSize: 11, lineHeight: 1.7 }}>
                Marking the observed outcome links a served score to reality. The model can then be
                recalibrated, the threshold re-tuned and retention offers compared against actual
                churn — without ever leaving the local database.
              </p>
            </article>
          </div>
        </>
      )}
    </>
  );
}
