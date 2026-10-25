import { useState } from "react";
import { Gauge, DriverRows, PriorityBadge, RiskBadge } from "./ui";
import { RISK, fmtMoney, fmtPct } from "../lib/format";

function SaveActionButton({ saved, onSave }) {
  const [busy, setBusy] = useState(false);
  if (saved) return <span className="saved">Saved to queue ✓</span>;
  return (
    <button
      type="button"
      className="btn ghost tiny"
      disabled={busy}
      onClick={async () => {
        setBusy(true);
        try {
          await onSave();
        } finally {
          setBusy(false);
        }
      }}
    >
      {busy ? "Saving…" : "Add to queue"}
    </button>
  );
}

export default function PredictionView({
  prediction,
  savedIds = [],
  onSave,
  hideHead = false,
}) {
  const savedSet = new Set(savedIds);
  const color = RISK[prediction.risk_level]?.color || RISK.low.color;
  const recs = prediction.recommendations || [];
  const drivers = prediction.top_drivers || [];

  return (
    <>
      {!hideHead ? (
        <div className="result-head">
          <div>
            <h3>{prediction.customer_id || "Ad-hoc profile"}</h3>
            <small>
              {prediction.model.name} · {prediction.model.version}
            </small>
          </div>
          <RiskBadge level={prediction.risk_level} />
        </div>
      ) : null}

      <div className="result-hero">
        <Gauge
          value={prediction.churn_probability}
          color={color}
          label="churn probability"
          variant="result"
        />
        <div className="result-meta">
          <div>
            <RiskBadge level={prediction.risk_level} />{" "}
            <span className="pill">
              {prediction.churn_prediction ? "Above threshold" : "Below threshold"}
            </span>
          </div>
          <h2>{prediction.churn_prediction ? "Likely to churn" : "Likely to stay"}</h2>
          <p>{prediction.summary}</p>
          <div className="threshold">
            Decision threshold <b>{fmtPct(prediction.threshold, 0)}</b> ·{" "}
            {RISK[prediction.risk_level]?.label || ""} band
          </div>
        </div>
      </div>

      <div className="fin-grid">
        <div className="fin">
          <span>Monthly charges</span>
          <strong>{fmtMoney(prediction.financial_impact.monthly_charges)}</strong>
        </div>
        <div className="fin">
          <span>Revenue at risk / yr</span>
          <strong>{fmtMoney(prediction.financial_impact.annual_revenue_at_risk)}</strong>
        </div>
        <div className="fin">
          <span>Estimated CLV</span>
          <strong>{fmtMoney(prediction.financial_impact.estimated_clv)}</strong>
        </div>
      </div>

      <div className="result-section-title">
        <span>Why this score</span>
        <span>SHAP contribution</span>
      </div>
      <DriverRows drivers={drivers} />

      <div className="result-section-title">
        <span>Retention playbook</span>
        <span>{recs.length} actions</span>
      </div>
      <div className="recommendations">
        {recs.map((recommendation) => (
          <article className="rec" key={recommendation.id}>
            <div className="rec-top">
              <strong>{recommendation.title}</strong>
              <PriorityBadge priority={recommendation.priority} />
            </div>
            <p>{recommendation.description}</p>
            <div className="rec-offer">{recommendation.offer}</div>
            <div className="rec-foot">
              <div className="rec-tags">
                <span className="rec-tag">{recommendation.category}</span>
                <span className="rec-tag">
                  {recommendation.expected_impact?.split(" - ")[0] || ""}
                </span>
              </div>
              {onSave ? (
                <SaveActionButton
                  saved={savedSet.has(recommendation.id)}
                  onSave={() => onSave(recommendation, prediction)}
                />
              ) : null}
            </div>
          </article>
        ))}
      </div>
    </>
  );
}
