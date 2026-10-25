import { useEffect, useState } from "react";
import {
  Activity,
  DollarSign,
  Inbox,
  Sparkles,
  Target,
  Users,
} from "lucide-react";
import {
  BarChart,
  CardHead,
  Donut,
  Gauge,
  HighRiskTable,
  ImportanceRows,
} from "../components/ui";
import { api } from "../api";
import { RISK, fmtCompact, fmtDate, fmtInt, fmtMoney, fmtPct } from "../lib/format";

export default function Overview({ core, openCustomer }) {
  const { summary, info, eda } = core;
  const [riskList, setRiskList] = useState([]);
  const [history, setHistory] = useState([]);

  useEffect(() => {
    let active = true;
    Promise.all([
      api("/customers/high-risk?limit=6").catch(() => ({ customers: [] })),
      api("/history?limit=4").catch(() => ({ items: [] })),
    ]).then(([customers, recent]) => {
      if (!active) return;
      setRiskList(customers.customers || []);
      setHistory(recent.items || []);
    });
    return () => {
      active = false;
    };
  }, []);

  const total = summary.customers.total || 1;
  const actions = summary.actions || {};
  const queue = [
    { key: "pending", value: actions.pending || 0 },
    { key: "contacted", value: actions.contacted || 0 },
    { key: "accepted", value: actions.accepted || 0 },
    { key: "declined", value: actions.declined || 0 },
  ];

  return (
    <>
      <section className="hero">
        <div className="hero-copy">
          <span className="eyebrow">AI-powered retention intelligence</span>
          <h1>
            Turn churn signals into <em>retention action.</em>
          </h1>
          <p>
            One command center for every at-risk customer: predictive scoring, transparent SHAP
            explanations, revenue exposure and the next best playbook action.
          </p>
          <div className="hero-actions">
            <a className="btn primary" href="#/predict">
              <Sparkles size={16} /> Score a customer
            </a>
            <a className="btn ghost" href="#/customers">
              <Users size={16} /> Review high-risk queue
            </a>
          </div>
          <div className="hero-stats">
            <div className="hero-stat">
              <strong>{fmtInt(summary.customers.total)}</strong>
              <small>customers scored</small>
            </div>
            <div className="hero-stat">
              <strong>{fmtPct(summary.customers.churn_rate)}</strong>
              <small>historical churn</small>
            </div>
            <div className="hero-stat">
              <strong>${fmtCompact(summary.revenue_at_risk.high)}</strong>
              <small>high-risk exposure</small>
            </div>
          </div>
        </div>

        <div className="hero-console">
          <div className="console-head">
            <strong>Priority signals</strong>
            <span className="live-pill">Live</span>
          </div>
          {riskList.length ? (
            riskList.slice(0, 4).map((customer) => (
              <div
                className="mini-customer"
                key={customer.customer_id}
                onClick={() => openCustomer(customer.customer_id)}
              >
                <div>
                  <strong>{customer.customer_id}</strong>
                  <small>
                    {customer.contract} · {customer.top_risk_driver || "risk profile"}
                  </small>
                </div>
                <span className="mini-prob">{fmtPct(customer.churn_probability, 0)}</span>
                <div className="mini-track">
                  <span style={{ width: `${customer.churn_probability * 100}%` }} />
                </div>
              </div>
            ))
          ) : (
            <div className="empty-state">
              <p>No high-risk customers in the current book.</p>
            </div>
          )}
          <div className="console-foot">
            <span>{fmtInt(summary.risk.high)} high-risk customers</span>
            <a href="#/customers">Open queue →</a>
          </div>
        </div>
      </section>

      <section className="kpi-grid">
        <article className="kpi">
          <div className="kpi-top">
            <span>Customer book</span>
            <span className="kpi-icon">
              <Users size={15} />
            </span>
          </div>
          <div className="kpi-value">{fmtInt(summary.customers.total)}</div>
          <div className="kpi-foot">
            <b>{fmtInt(summary.customers.retained)}</b> retained ·{" "}
            {fmtInt(summary.customers.churned)} churned
          </div>
          <div className="kpi-bar">
            <span style={{ width: "100%" }} />
          </div>
        </article>
        <article className="kpi">
          <div className="kpi-top">
            <span>Churn rate</span>
            <span className="kpi-icon">
              <Activity size={15} />
            </span>
          </div>
          <div className="kpi-value">{fmtPct(summary.customers.churn_rate)}</div>
          <div className="kpi-foot">
            IBM Telco base rate · <b>{fmtInt(summary.customers.churned)}</b> churners
          </div>
          <div className="kpi-bar amber">
            <span style={{ width: `${Math.min(100, summary.customers.churn_rate * 230)}%` }} />
          </div>
        </article>
        <article className="kpi">
          <div className="kpi-top">
            <span>High-risk customers</span>
            <span className="kpi-icon">
              <Target size={15} />
            </span>
          </div>
          <div className="kpi-value">{fmtInt(summary.risk.high)}</div>
          <div className="kpi-foot">
            <b className="red">{fmtPct(summary.risk.high / total)}</b> of the book ·{" "}
            {fmtInt(summary.risk.medium)} medium
          </div>
          <div className="kpi-bar red">
            <span style={{ width: `${Math.min(100, (summary.risk.high / total) * 400)}%` }} />
          </div>
        </article>
        <article className="kpi">
          <div className="kpi-top">
            <span>Revenue at risk</span>
            <span className="kpi-icon">
              <DollarSign size={15} />
            </span>
          </div>
          <div className="kpi-value">{fmtMoney(summary.revenue_at_risk.high)}</div>
          <div className="kpi-foot">
            Annualised high-risk exposure · <b>{fmtMoney(summary.revenue_at_risk.total)}</b> total
          </div>
          <div className="kpi-bar">
            <span
              style={{
                width: `${Math.min(
                  100,
                  (summary.revenue_at_risk.high / Math.max(1, summary.revenue_at_risk.total)) * 100
                )}%`,
              }}
            />
          </div>
        </article>
      </section>

      <section className="grid">
        <article className="card span-4">
          <CardHead title="Risk distribution" sub="Customers by predicted churn band" />
          <div className="donut-layout">
            <Donut risk={summary.risk} total={total} />
            <div className="legend">
              {["high", "medium", "low"].map((level) => (
                <div className="legend-row" key={level}>
                  <span className="dot" style={{ background: RISK[level].color }} />
                  <div>
                    <span>{RISK[level].label} risk</span>
                    <strong>{fmtInt(summary.risk[level])}</strong>
                    <small>{fmtPct(summary.risk[level] / total)} of book</small>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </article>

        <article className="card span-5">
          <CardHead
            title="Churn by contract"
            sub="Historical churn rate within each contract type"
            action={
              <a className="card-action" href="#/insights">
                Explore →
              </a>
            }
          />
          {eda ? (
            <BarChart items={eda.churn_by_contract} />
          ) : (
            <div className="empty-state">
              <p>EDA data unavailable.</p>
            </div>
          )}
        </article>

        <article className="card span-3">
          <CardHead
            title="Model performance"
            sub="Held-out test set"
            action={
              <a className="card-action" href="#/insights">
                Metrics →
              </a>
            }
          />
          <div className="gauge-wrap">
            <Gauge value={summary.model.test_roc_auc} label="ROC-AUC" />
            <div className="metrics-list">
              <div className="metric-row">
                <span>Recall @ {fmtPct(summary.model.threshold, 0)}</span>
                <strong>{fmtPct(summary.model.recall)}</strong>
              </div>
              <div className="metric-row">
                <span>Precision</span>
                <strong>{fmtPct(summary.model.precision)}</strong>
              </div>
              <div className="metric-row">
                <span>F1 score</span>
                <strong>{Number(summary.model.f1 || 0).toFixed(3)}</strong>
              </div>
              <div className="metric-row">
                <span>Brier score</span>
                <strong>{Number(summary.model.brier || 0).toFixed(3)}</strong>
              </div>
            </div>
          </div>
        </article>
      </section>

      <section className="grid">
        <article className="card span-5">
          <CardHead title="Global churn drivers" sub="Mean absolute SHAP impact, aggregated by source" />
          <ImportanceRows rows={(info.global_importance || []).slice(0, 7)} />
          <div className="rec-offer" style={{ marginTop: 16 }}>
            Contract, internet service and tenure carry most of the signal. Open Model insights for
            the full SHAP beeswarm and calibration plots.
          </div>
          <div style={{ marginTop: 12 }}>
            <a className="btn ghost small" href="#/insights">
              <Activity size={15} /> Explain the model
            </a>
          </div>
        </article>

        <article className="card span-7">
          <CardHead
            title="Highest-risk customers"
            sub="Ranked by predicted churn probability"
            action={
              <a className="card-action" href="#/customers">
                View all →
              </a>
            }
          />
          <HighRiskTable customers={riskList} onOpen={openCustomer} />
        </article>
      </section>

      <section className="grid">
        <article className="card span-4">
          <CardHead title="Retention queue" sub="Actions saved by the team" />
          <div className="grid" style={{ gridTemplateColumns: "repeat(2,1fr)", margin: 0, gap: 9 }}>
            {queue.map((item) => (
              <div className="fin" key={item.key}>
                <span>{item.key}</span>
                <strong
                  style={{
                    color:
                      item.key === "pending"
                        ? "var(--amber)"
                        : item.key === "accepted"
                          ? "var(--green)"
                          : item.key === "declined"
                            ? "var(--red)"
                            : "var(--blue)",
                  }}
                >
                  {fmtInt(item.value)}
                </strong>
              </div>
            ))}
          </div>
          <div style={{ marginTop: 14 }}>
            <a className="btn ghost small" href="#/queue">
              <Inbox size={15} /> Open action queue
            </a>
          </div>
        </article>

        <article className="card span-4">
          <CardHead
            title="Recent scores"
            sub="Audit trail, newest first"
            action={
              <a className="card-action" href="#/history">
                History →
              </a>
            }
          />
          {history.length ? (
            <div className="segment-list">
              {history.map((item) => (
                <div className="segment-row" key={item.id}>
                  <span>
                    {item.customer_id || "Ad-hoc"}
                    <br />
                    <small style={{ color: "#466158" }}>{fmtDate(item.created_at)}</small>
                  </span>
                  <div className="segment-track">
                    <i style={{ width: `${item.churn_probability * 100}%` }} />
                  </div>
                  <strong>{fmtPct(item.churn_probability, 0)}</strong>
                </div>
              ))}
            </div>
          ) : (
            <div className="empty-state">
              <p>No predictions logged yet. Score a customer to begin the audit trail.</p>
            </div>
          )}
        </article>

        <article className="card span-4">
          <CardHead title="Database" sub="Operational store is healthy" />
          <div className="segment-list">
            <div className="segment-row">
              <span>Engine</span>
              <div className="segment-track">
                <i style={{ width: "100%" }} />
              </div>
              <strong>SQLite</strong>
            </div>
            <div className="segment-row">
              <span>Predictions</span>
              <div className="segment-track">
                <i
                  style={{
                    width: `${Math.min(100, (summary.history?.total_predictions || 0) * 2)}%`,
                  }}
                />
              </div>
              <strong>{fmtInt(summary.history?.total_predictions || 0)}</strong>
            </div>
            <div className="segment-row">
              <span>Actions</span>
              <div className="segment-track">
                <i style={{ width: `${Math.min(100, (actions.total || 0) * 8)}%` }} />
              </div>
              <strong>{fmtInt(actions.total || 0)}</strong>
            </div>
          </div>
          <p className="card-sub" style={{ marginTop: 14 }}>
            No sign-in required. Feedback and saved actions persist locally in{" "}
            <span className="mono">data/processed/churn.db</span>.
          </p>
        </article>
      </section>
    </>
  );
}
