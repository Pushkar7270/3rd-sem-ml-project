import { useState } from "react";
import { DollarSign, Sparkles, Users } from "lucide-react";
import { EmptyState, PageHead } from "../components/ui";
import PredictionView from "../components/PredictionView";
import { api } from "../api";
import {
  FIELD_CONFIG,
  highRiskProfile,
  lowRiskProfile,
  readProfile,
} from "../lib/format";

const GROUPS = [
  {
    title: "Account",
    icon: Users,
    fields: ["customerID", "gender", "SeniorCitizen", "Partner", "Dependents", "tenure"],
  },
  {
    title: "Services",
    icon: Sparkles,
    fields: [
      "PhoneService",
      "MultipleLines",
      "InternetService",
      "OnlineSecurity",
      "OnlineBackup",
      "DeviceProtection",
      "TechSupport",
      "StreamingTV",
      "StreamingMovies",
    ],
  },
  {
    title: "Billing",
    icon: DollarSign,
    fields: ["Contract", "PaperlessBilling", "PaymentMethod", "MonthlyCharges", "TotalCharges"],
  },
];

function Field({ config, value, onChange }) {
  const id = `field-${config.name}`;
  return (
    <div className="field">
      <label htmlFor={id}>{config.label}</label>
      {config.type === "select" ? (
        <select id={id} value={value ?? ""} onChange={(event) => onChange(config.name, event.target.value)}>
          {config.options.map((option) => {
            const optionValue = Array.isArray(option) ? option[0] : option;
            const optionLabel = Array.isArray(option) ? option[1] : option;
            return (
              <option value={optionValue} key={String(optionValue)}>
                {optionLabel}
              </option>
            );
          })}
        </select>
      ) : (
        <input
          id={id}
          type={config.type}
          value={value ?? ""}
          placeholder={config.placeholder || ""}
          min={config.min}
          max={config.max}
          step={config.step || "any"}
          onChange={(event) => onChange(config.name, event.target.value)}
        />
      )}
    </div>
  );
}

export default function Predict({ toast, refreshCore }) {
  const [profile, setProfile] = useState(highRiskProfile);
  const [result, setResult] = useState(null);
  const [savedIds, setSavedIds] = useState([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const setField = (name, value) => {
    setProfile((current) => ({ ...current, [name]: value }));
  };

  const applyProfile = (next) => {
    setProfile(next);
    setResult(null);
    setError("");
    setSavedIds([]);
  };

  const submit = async (event) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    setResult(null);
    setSavedIds([]);
    try {
      const prediction = await api("/predict", {
        method: "POST",
        body: JSON.stringify(readProfile(profile)),
      });
      setResult(prediction);
      toast(
        `Scored ${prediction.customer_id || "profile"} · ${(prediction.churn_probability * 100).toFixed(
          1
        )}% churn risk`
      );
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const saveAction = async (recommendation, prediction) => {
    if (!prediction.customer_id) {
      toast("Add a customer ID before saving an action", "error");
      throw new Error("Missing customer ID");
    }
    try {
      await api("/actions", {
        method: "POST",
        body: JSON.stringify({
          customer_id: prediction.customer_id,
          recommendation_id: recommendation.id,
          title: recommendation.title,
          offer: recommendation.offer,
          risk_level: prediction.risk_level,
          churn_probability: prediction.churn_probability,
        }),
      });
      setSavedIds((current) => [...current, recommendation.id]);
      toast("Action saved to the retention queue");
      if (refreshCore) await refreshCore();
    } catch (err) {
      toast(err.message, "error");
      throw err;
    } finally {
      setSavingId(null);
    }
  };

  return (
    <>
      <PageHead
        eyebrow="Explainable scoring"
        title="Score a customer profile"
        sub="Submit raw customer attributes. The model returns a probability, risk band, signed SHAP drivers and a ranked retention playbook."
      />

      <div className="grid">
        <div className="span-7">
          <article className="card form-card">
            <form onSubmit={submit}>
              {GROUPS.map((group) => {
                const Icon = group.icon;
                return (
                  <div className="form-section" key={group.title}>
                    <h3 className="section-title">
                      <span>
                        <Icon size={11} />
                      </span>{" "}
                      {group.title}
                    </h3>
                    <div className="form-grid">
                      {group.fields.map((name) => {
                        const config = FIELD_CONFIG.find((field) => field.name === name);
                        if (!config) return null;
                        return (
                          <Field
                            key={name}
                            config={config}
                            value={profile[name]}
                            onChange={setField}
                          />
                        );
                      })}
                    </div>
                  </div>
                );
              })}
              <div className="form-actions">
                <button className="btn primary" type="submit" disabled={busy}>
                  <Sparkles size={16} /> {busy ? "Scoring…" : "Score customer"}
                </button>
                <button
                  className="btn ghost small"
                  type="button"
                  onClick={() => {
                    applyProfile(highRiskProfile());
                    toast("High-risk demo profile loaded");
                  }}
                >
                  High-risk demo
                </button>
                <button
                  className="btn ghost small"
                  type="button"
                  onClick={() => {
                    applyProfile(lowRiskProfile());
                    toast("Low-risk demo profile loaded");
                  }}
                >
                  Low-risk demo
                </button>
                <span className="form-note">Required: tenure, monthly charges</span>
              </div>
              {error ? <div className="form-error">{error}</div> : null}
            </form>
          </article>
        </div>

        <div className="span-5">
          <article className="card">
            {busy ? (
              <div className="result-empty">
                <div className="loader-ring" />
                <p>Computing probability and SHAP explanations…</p>
              </div>
            ) : result ? (
              <PredictionView
                prediction={result}
                savedIds={savedIds}
                onSave={saveAction}
              />
            ) : (
              <div className="result-empty">
                <div className="orb">
                  <Sparkles size={28} />
                </div>
                <h3>Your result will appear here</h3>
                <p>
                  Score a profile to see the churn probability, the top SHAP drivers and a
                  prioritised retention playbook.
                </p>
              </div>
            )}
          </article>
        </div>
      </div>
    </>
  );
}
