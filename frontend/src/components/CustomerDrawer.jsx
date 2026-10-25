import { useEffect, useState } from "react";
import { X } from "lucide-react";
import { api } from "../api";
import PredictionView from "./PredictionView";
import { EmptyState } from "./ui";

export default function CustomerDrawer({ customerId, onClose, toast, onSaved }) {
  const [detail, setDetail] = useState(null);
  const [savedIds, setSavedIds] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!customerId) {
      setDetail(null);
      setSavedIds([]);
      setError("");
      setLoading(false);
      return undefined;
    }
    let active = true;
    setLoading(true);
    setError("");
    setDetail(null);
    setSavedIds([]);
    Promise.all([
      api(`/customers/${encodeURIComponent(customerId)}`),
      api(`/actions?customer_id=${encodeURIComponent(customerId)}&limit=100`).catch(() => ({
        actions: [],
      })),
    ])
      .then(([prediction, saved]) => {
        if (!active) return;
        setDetail(prediction);
        setSavedIds((saved.actions || []).map((action) => action.recommendation_id));
      })
      .catch((err) => {
        if (active) setError(err.message);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [customerId]);

  useEffect(() => {
    if (!customerId) return undefined;
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previous;
    };
  }, [customerId]);

  const saveAction = async (recommendation, prediction) => {
    try {
      await api("/actions", {
        method: "POST",
        body: JSON.stringify({
          customer_id: prediction.customer_id || customerId,
          recommendation_id: recommendation.id,
          title: recommendation.title,
          offer: recommendation.offer,
          risk_level: prediction.risk_level,
          churn_probability: prediction.churn_probability,
        }),
      });
      setSavedIds((current) => [...current, recommendation.id]);
      toast("Action saved to the retention queue");
      if (onSaved) await onSaved();
    } catch (err) {
      toast(err.message, "error");
      throw err;
    }
  };

  return (
    <>
      <div
        className={`drawer-backdrop ${customerId ? "open" : ""}`}
        hidden={!customerId}
        onClick={onClose}
      />
      <aside
        className={`drawer ${customerId ? "open" : ""}`}
        aria-hidden={!customerId}
        aria-label="Customer details"
      >
        <div className="drawer-head">
          <div>
            <h2>{customerId || "Customer"}</h2>
            <small>Live score · SHAP explanation · retention playbook</small>
          </div>
          <button className="drawer-close" onClick={onClose} aria-label="Close">
            <X size={16} />
          </button>
        </div>
        <div className="drawer-body">
          {loading ? (
            <div className="result-empty">
              <div className="loader-ring" />
              <p>Loading customer, SHAP drivers and playbook…</p>
            </div>
          ) : error ? (
            <EmptyState title="Could not load customer" text={error} />
          ) : detail ? (
            <PredictionView
              prediction={detail}
              savedIds={savedIds}
              onSave={saveAction}
              hideHead
            />
          ) : null}
        </div>
      </aside>
    </>
  );
}
