import { ArrowRight, Inbox, ShieldCheck } from "lucide-react";
import { RISK, fmtInt, fmtPct, fmtCert } from "../lib/format";

export function PageHead({ eyebrow, title, sub, actions = null }) {
  return (
    <div className="page-head">
      <div>
        <span className="eyebrow">{eyebrow}</span>
        <h1 className="page-title">{title}</h1>
        <p className="page-sub">{sub}</p>
      </div>
      {actions ? <div className="head-actions">{actions}</div> : null}
    </div>
  );
}

export function CardHead({ title, sub = "", action = null }) {
  return (
    <div className="card-head">
      <div>
        <h3 className="card-title">{title}</h3>
        {sub ? <p className="card-sub">{sub}</p> : null}
      </div>
      {action}
    </div>
  );
}

export function RiskBadge({ level }) {
  const safe = RISK[level] ? level : "low";
  return <span className={`badge ${safe}`}>{RISK[safe].label}</span>;
}

export function PriorityBadge({ priority }) {
  return <span className={`priority ${priority}`}>{priority}</span>;
}

export function StatusPill({ status }) {
  return <span className={`status-pill ${status}`}>{status}</span>;
}

export function Gauge({ value, color = "#2ff0a3", label = "churn risk", variant = "gauge" }) {
  const radius = 50;
  const circumference = 2 * Math.PI * radius;
  const dash = Math.max(0, Math.min(1, Number(value || 0))) * circumference;
  const wrapper = variant === "result" ? "result-prob" : "gauge";
  return (
    <div className={wrapper}>
      <svg viewBox="0 0 128 128" width="100%" height="100%">
        <circle className="gauge-bg" cx="64" cy="64" r={radius} />
        <circle
          className="gauge-fill"
          cx="64"
          cy="64"
          r={radius}
          stroke={color}
          strokeDasharray={`${dash} ${circumference}`}
          strokeDashoffset="0"
        />
      </svg>
      <div className={variant === "result" ? "center" : "gauge-center"}>
        <strong style={{ color }}>{fmtPct(value)}</strong>
        <small>{label}</small>
      </div>
    </div>
  );
}

export function Donut({ risk, total }) {
  const radius = 62;
  const circumference = 2 * Math.PI * radius;
  const items = [
    { key: "high", value: risk.high || 0, color: RISK.high.color },
    { key: "medium", value: risk.medium || 0, color: RISK.medium.color },
    { key: "low", value: risk.low || 0, color: RISK.low.color },
  ];
  let offset = 0;
  const circles = items.map((item) => {
    const dash = total ? (item.value / total) * circumference : 0;
    const gap = Math.min(3, dash / 3);
    const segment = Math.max(0, dash - gap);
    const circle = (
      <circle
        key={item.key}
        cx="84"
        cy="84"
        r={radius}
        stroke={item.color}
        strokeDasharray={`${segment} ${circumference - segment}`}
        strokeDashoffset={-offset}
      />
    );
    offset += dash;
    return circle;
  });
  return (
    <div className="donut">
      <svg viewBox="0 0 168 168">{circles}</svg>
      <div className="donut-center">
        <strong>{fmtInt(risk.high || 0)}</strong>
        <small>high risk</small>
      </div>
    </div>
  );
}

export function BarChart({ items, valueKey = "churn_rate" }) {
  const max = Math.max(0.01, ...items.map((item) => Number(item[valueKey] || 0)));
  return (
    <div className="bar-chart">
      {items.map((item, index) => (
        <div className="bar-col" key={item.segment || index}>
          <span className="bar-value">{fmtPct(item[valueKey])}</span>
          <div className="bar-track">
            <div
              className="bar-fill"
              style={{ height: `${Math.max(5, (Number(item[valueKey] || 0) / max) * 100)}%` }}
            />
          </div>
          <span className="bar-label">
            {item.segment}
            <br />
            <span style={{ color: "#3f574e" }}>{fmtInt(item.customers)}</span>
          </span>
        </div>
      ))}
    </div>
  );
}

export function SegmentRows({ items, valueKey = "churn_rate" }) {
  const max = Math.max(0.01, ...items.map((item) => Number(item[valueKey] || 0)));
  return (
    <div className="segment-list">
      {items.map((item) => (
        <div className="segment-row" key={item.segment}>
          <span title={item.segment}>{item.segment}</span>
          <div className="segment-track">
            <i style={{ width: `${(Number(item[valueKey] || 0) / max) * 100}%` }} />
          </div>
          <strong>{fmtPct(item[valueKey])}</strong>
        </div>
      ))}
    </div>
  );
}

export function ImportanceRows({ rows }) {
  if (!rows?.length) {
    return (
      <div className="empty-state">
        <p>No importance data available.</p>
      </div>
    );
  }
  const max = Math.max(0.0001, ...rows.map((row) => row.importance));
  return (
    <div className="segment-list">
      {rows.map((row) => (
        <div className="segment-row" key={row.feature || row.label}>
          <span title={row.label}>{row.label}</span>
          <div className="segment-track">
            <i style={{ width: `${(row.importance / max) * 100}%` }} />
          </div>
          <strong style={{ color: "#91aaa0" }}>{fmtCert(row.importance)}</strong>
        </div>
      ))}
    </div>
  );
}

export function DriverRows({ drivers }) {
  if (!drivers?.length) {
    return (
      <div className="empty-state">
        <p>No driver detail returned.</p>
      </div>
    );
  }
  const max = Math.max(0.0001, ...drivers.map((driver) => Math.abs(driver.contribution)));
  return (
    <div className="driver-list">
      {drivers.map((driver, index) => {
        const positive = driver.contribution > 0;
        return (
          <div
            className="driver-row"
            key={`${driver.source}-${index}`}
            title={`${driver.label} = ${driver.value} (${driver.impact})`}
          >
            <span className="driver-name">
              {driver.label}
              {driver.value !== null && driver.value !== undefined ? (
                <span style={{ color: "#4f695f" }}> = {String(driver.value)}</span>
              ) : null}
            </span>
            <div className="driver-track">
              <span
                className={`driver-fill ${positive ? "pos" : "neg"}`}
                style={{ width: `${(Math.abs(driver.contribution) / max) * 50}%` }}
              />
            </div>
            <span className={`driver-value ${positive ? "pos" : "neg"}`}>
              {positive ? "+" : ""}
              {Number(driver.contribution).toFixed(2)}
            </span>
          </div>
        );
      })}
    </div>
  );
}

export function HighRiskTable({ customers, onOpen }) {
  if (!customers?.length) {
    return (
      <EmptyState
        icon={<ShieldCheck size={24} />}
        title="No customers in this band"
        text="Try another risk band or refresh the customer book."
      />
    );
  }
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Customer</th>
            <th>Risk</th>
            <th>Probability</th>
            <th>Tenure</th>
            <th>Contract</th>
            <th>Top risk driver</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {customers.map((customer) => (
            <tr
              className="row-link"
              key={customer.customer_id}
              onClick={() => onOpen(customer.customer_id)}
            >
              <td>
                <strong>{customer.customer_id}</strong>
                <span className="sub">
                  {customer.internet_service} · {customer.payment_method}
                </span>
              </td>
              <td>
                <RiskBadge level={customer.risk_level} />
              </td>
              <td>
                <div className="cell-prob">
                  <div className="prob-track">
                    <span
                      className={customer.risk_level}
                      style={{ width: `${customer.churn_probability * 100}%` }}
                    />
                  </div>
                  <strong>{fmtPct(customer.churn_probability, 0)}</strong>
                </div>
              </td>
              <td>{fmtInt(customer.tenure)} mo</td>
              <td>{customer.contract}</td>
              <td>{customer.top_risk_driver || <span className="muted">—</span>}</td>
              <td>
                <ArrowRight size={14} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function EmptyState({ icon = <Inbox size={24} />, title, text, action = null }) {
  return (
    <div className="empty-state">
      <div className="empty-icon">{icon}</div>
      <h3>{title}</h3>
      <p>{text}</p>
      {action ? <div style={{ marginTop: 14 }}>{action}</div> : null}
    </div>
  );
}

export function SkeletonPage() {
  return (
    <>
      <div className="grid">
        <div className="span-12 skeleton" style={{ height: 240 }} />
      </div>
      <div className="kpi-grid">
        {[1, 2, 3, 4].map((item) => (
          <div className="skeleton skeleton-card" key={item} />
        ))}
      </div>
      <div className="grid">
        <div className="span-5 skeleton" style={{ height: 300 }} />
        <div className="span-7 skeleton" style={{ height: 300 }} />
      </div>
    </>
  );
}
