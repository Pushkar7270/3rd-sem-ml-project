import { useEffect, useState } from "react";
import { Activity, BarChart3, FileText, ShieldCheck, Target } from "lucide-react";
import { CardHead, ImportanceRows, PageHead, SegmentRows } from "../components/ui";
import { api } from "../api";
import {
  MODEL_COLORS,
  MODEL_LABELS,
  fmtCert,
  fmtInt,
  fmtPct,
} from "../lib/format";

const GALLERY = [
  ["shap_summary.png", "SHAP beeswarm — direction and magnitude of every feature"],
  ["roc_curves.png", "ROC curves — all six candidate models"],
  ["pr_curves.png", "Precision-recall curves — churn is the minority class"],
  ["calibration.png", "Calibration — predicted vs observed churn rate"],
  ["churn_by_segment.png", "Exploratory segment analysis"],
  ["confusion_matrix.png", "Confusion matrix at the tuned threshold"],
];

function RocChart({ curves, selected }) {
  const names = Object.keys(curves || {});
  if (!names.length) {
    return (
      <div className="empty-state">
        <p>Curve data unavailable.</p>
      </div>
    );
  }
  const width = 430;
  const height = 245;
  const pad = { left: 38, right: 12, top: 12, bottom: 30 };
  const plotW = width - pad.left - pad.right;
  const plotH = height - pad.top - pad.bottom;
  const x = (value) => pad.left + value * plotW;
  const y = (value) => pad.top + (1 - value) * plotH;
  const path = (points) =>
    points.fpr
      .map(
        (value, index) =>
          `${index === 0 ? "M" : "L"}${x(value).toFixed(2)},${y(points.tpr[index]).toFixed(2)}`
      )
      .join(" ");
  const order = names
    .filter((name) => name !== selected)
    .concat(names.filter((name) => name === selected));
  const grid = [0, 0.25, 0.5, 0.75, 1];

  return (
    <>
      <svg className="chart-svg" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="ROC curves">
        {grid.map((tick) => (
          <g key={tick}>
            <line className="grid-line" x1={x(tick)} y1={y(0)} x2={x(tick)} y2={y(1)} />
            <line className="grid-line" x1={x(0)} y1={y(tick)} x2={x(1)} y2={y(tick)} />
            <text className="axis-text" x={x(tick)} y={height - 9} textAnchor="middle">
              {tick}
            </text>
            <text className="axis-text" x={pad.left - 8} y={y(tick) + 3} textAnchor="end">
              {tick}
            </text>
          </g>
        ))}
        <line
          x1={x(0)}
          y1={y(0)}
          x2={x(1)}
          y2={y(1)}
          stroke="rgba(137,255,199,.14)"
          strokeDasharray="3 4"
        />
        {order.map((name) => {
          const points = curves[name];
          if (!points?.fpr?.length) return null;
          const isSelected = name === selected;
          return (
            <path
              className={`roc-line ${isSelected ? "roc-selected" : ""}`}
              key={name}
              d={path(points)}
              stroke={MODEL_COLORS[name] || "#5f7d70"}
              strokeOpacity={isSelected ? 1 : 0.28}
              strokeWidth={isSelected ? 2.6 : 1.1}
            />
          );
        })}
        <text className="axis-text" x={x(0.5)} y={height - 1} textAnchor="middle">
          False positive rate
        </text>
        <text
          className="axis-text"
          x={11}
          y={y(0.5)}
          textAnchor="middle"
          transform={`rotate(-90 11 ${y(0.5)})`}
        >
          True positive rate
        </text>
      </svg>
      <div className="roc-legend">
        {names.map((name) => (
          <span key={name}>
            <i
              style={{
                background: MODEL_COLORS[name] || "#5f7d70",
                opacity: name === selected ? 1 : 0.45,
              }}
            />
            {MODEL_LABELS[name] || name}
            {name === selected ? " · deployed" : ""}
          </span>
        ))}
      </div>
    </>
  );
}

export default function Insights({ core }) {
  const { metrics, info, eda } = core;
  const [figures, setFigures] = useState([]);

  useEffect(() => {
    api("/figures")
      .then((data) => setFigures(data.figures || []))
      .catch(() => setFigures([]));
  }, []);

  const modelName = info.model.name;
  const cv = metrics.cv_results || {};
  const test = metrics.test_results || {};
  const order = Object.keys(cv).sort(
    (a, b) => (cv[b].roc_auc.mean || 0) - (cv[a].roc_auc.mean || 0)
  );
  const galleryMap = Object.fromEntries(figures.map((figure) => [figure.name, figure.url]));

  return (
    <>
      <PageHead
        eyebrow="Evidence & explainability"
        title="Model insights"
        sub="The deployed model, its held-out performance, the drivers behind its decisions and the data story behind churn."
        actions={
          <a className="btn ghost small" href="/model/card" target="_blank" rel="noreferrer">
            <FileText size={15} /> Model card
          </a>
        }
      />

      <section className="kpi-grid">
        <article className="kpi">
          <div className="kpi-top">
            <span>CV ROC-AUC</span>
            <span className="kpi-icon">
              <BarChart3 size={15} />
            </span>
          </div>
          <div className="kpi-value">{fmtCert(cv[modelName]?.roc_auc?.mean)}</div>
          <div className="kpi-foot">
            5-fold cross-validation · σ {fmtCert(cv[modelName]?.roc_auc?.std)}
          </div>
          <div className="kpi-bar">
            <span style={{ width: `${(cv[modelName]?.roc_auc?.mean || 0) * 100}%` }} />
          </div>
        </article>
        <article className="kpi">
          <div className="kpi-top">
            <span>Test ROC-AUC</span>
            <span className="kpi-icon">
              <Target size={15} />
            </span>
          </div>
          <div className="kpi-value">{fmtCert(info.test_metrics?.roc_auc)}</div>
          <div className="kpi-foot">
            Held-out set · {fmtInt(info.dataset?.test_rows)} customers
          </div>
          <div className="kpi-bar">
            <span style={{ width: `${(info.test_metrics?.roc_auc || 0) * 100}%` }} />
          </div>
        </article>
        <article className="kpi">
          <div className="kpi-top">
            <span>Recall @ {fmtPct(info.threshold, 0)}</span>
            <span className="kpi-icon">
              <ShieldCheck size={15} />
            </span>
          </div>
          <div className="kpi-value">{fmtPct(info.test_metrics?.recall)}</div>
          <div className="kpi-foot">
            Precision {fmtPct(info.test_metrics?.precision)} · F1{" "}
            {fmtCert(info.test_metrics?.f1)}
          </div>
          <div className="kpi-bar amber">
            <span style={{ width: `${(info.test_metrics?.recall || 0) * 100}%` }} />
          </div>
        </article>
        <article className="kpi">
          <div className="kpi-top">
            <span>Brier score</span>
            <span className="kpi-icon">
              <Activity size={15} />
            </span>
          </div>
          <div className="kpi-value">{fmtCert(info.test_metrics?.brier)}</div>
          <div className="kpi-foot">Probability calibration · lower is better</div>
          <div className="kpi-bar">
            <span
              style={{ width: `${Math.max(8, (1 - (info.test_metrics?.brier || 0)) * 100)}%` }}
            />
          </div>
        </article>
      </section>

      <section className="grid">
        <article className="card span-7">
          <CardHead
            title="Model comparison"
            sub="5-fold CV selection on ROC-AUC; test metrics at threshold 0.5"
            action={<span className="pill">Selected: {MODEL_LABELS[modelName] || modelName}</span>}
          />
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Model</th>
                  <th>CV ROC-AUC</th>
                  <th>Test ROC-AUC</th>
                  <th>Recall</th>
                  <th>F1</th>
                  <th>Brier</th>
                </tr>
              </thead>
              <tbody>
                {order.map((name) => {
                  const cvMetric = cv[name]?.roc_auc || {};
                  const testMetric = test[name] || {};
                  return (
                    <tr className={name === modelName ? "model-row-selected" : ""} key={name}>
                      <td>
                        <strong>{MODEL_LABELS[name] || name}</strong>
                        {name === modelName ? <span className="sub">deployed</span> : null}
                      </td>
                      <td>
                        {fmtCert(cvMetric.mean)}{" "}
                        <span className="muted">± {fmtCert(cvMetric.std)}</span>
                      </td>
                      <td>{fmtCert(testMetric.roc_auc)}</td>
                      <td>{fmtPct(testMetric.recall)}</td>
                      <td>{fmtCert(testMetric.f1)}</td>
                      <td>{fmtCert(testMetric.brier)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </article>
        <article className="card span-5">
          <CardHead title="ROC curve" sub="Held-out test set · 60-point downsampled" />
          <RocChart curves={metrics.curves || {}} selected={modelName} />
        </article>
      </section>

      <section className="grid">
        <article className="card span-5">
          <CardHead title="Key churn drivers" sub="Mean absolute SHAP value by source feature" />
          <ImportanceRows rows={(info.global_importance || []).slice(0, 9)} />
          <p className="card-sub" style={{ marginTop: 14 }}>
            SHAP values are conditional explanations, not causal effects. Use the per-customer{" "}
            <code>top_risk_driver</code> for outreach copy.
          </p>
        </article>
        <article className="card span-7">
          <CardHead
            title="Churn by customer segment"
            sub="Historical churn rate across the IBM Telco book"
          />
          <div className="grid" style={{ gridTemplateColumns: "1fr 1fr", margin: 0, gap: 18 }}>
            <div>
              <CardHead title="Contract" />
              {eda ? <SegmentRows items={eda.churn_by_contract} /> : <p className="muted">Unavailable</p>}
            </div>
            <div>
              <CardHead title="Internet service" />
              {eda ? <SegmentRows items={eda.churn_by_internet} /> : <p className="muted">Unavailable</p>}
            </div>
            <div>
              <CardHead title="Payment method" />
              {eda ? <SegmentRows items={eda.churn_by_payment} /> : <p className="muted">Unavailable</p>}
            </div>
            <div>
              <CardHead title="Tenure bucket" />
              {eda ? (
                <SegmentRows items={eda.churn_by_tenure_bucket} />
              ) : (
                <p className="muted">Unavailable</p>
              )}
            </div>
          </div>
        </article>
      </section>

      <section className="card">
        <CardHead
          title="Explainability gallery"
          sub="Generated during training · click to open full size"
          action={
            <a className="card-action" href="/reports/model_card.md" target="_blank" rel="noreferrer">
              Model card →
            </a>
          }
        />
        <div className="gallery">
          {GALLERY.filter(([name]) => galleryMap[name]).map(([name, caption]) => (
            <figure key={name}>
              <a href={galleryMap[name]} target="_blank" rel="noreferrer">
                <img loading="lazy" src={galleryMap[name]} alt={caption} />
              </a>
              <figcaption>{caption}</figcaption>
            </figure>
          ))}
        </div>
      </section>
    </>
  );
}
