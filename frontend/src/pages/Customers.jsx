import { useEffect, useMemo, useState } from "react";
import { Download, Search } from "lucide-react";
import { EmptyState, HighRiskTable, PageHead } from "../components/ui";
import { api } from "../api";
import { fmtInt } from "../lib/format";

const BANDS = [
  { id: "high", label: "High risk" },
  { id: "medium", label: "Medium" },
  { id: "low", label: "Low" },
];

export default function Customers({ openCustomer, toast }) {
  const [band, setBand] = useState("high");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [list, setList] = useState([]);
  const [totalMatching, setTotalMatching] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");
    api(`/customers/high-risk?risk_level=${band}&limit=500`)
      .then((data) => {
        if (!active) return;
        setList(data.customers || []);
        setTotalMatching(data.total_matching || 0);
        setPage(1);
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
  }, [band]);

  const filtered = useMemo(() => {
    const query = search.trim().toLowerCase();
    if (!query) return list;
    return list.filter((customer) =>
      [
        customer.customer_id,
        customer.contract,
        customer.internet_service,
        customer.payment_method,
        customer.top_risk_driver,
      ]
        .join(" ")
        .toLowerCase()
        .includes(query)
    );
  }, [list, search]);

  useEffect(() => {
    setPage(1);
  }, [search]);

  const pageSize = 10;
  const pages = Math.max(1, Math.ceil(filtered.length / pageSize));
  const currentPage = Math.min(page, pages);
  const start = (currentPage - 1) * pageSize;
  const pageRows = filtered.slice(start, start + pageSize);
  const firstPage = Math.max(1, Math.min(currentPage - 2, pages - 4));
  const pageNumbers = Array.from({ length: Math.min(5, pages) }, (_, index) => firstPage + index).filter(
    (number) => number <= pages
  );

  const exportCsv = () => {
    if (!list.length) {
      toast("No customers to export", "error");
      return;
    }
    const headers = [
      "customer_id",
      "risk_level",
      "churn_probability",
      "tenure",
      "contract",
      "internet_service",
      "payment_method",
      "monthly_charges",
      "top_risk_driver",
    ];
    const csv = [
      headers.join(","),
      ...list.map((row) =>
        headers
          .map((key) => `"${String(row[key] ?? "").replace(/"/g, '""')}"`)
          .join(",")
      ),
    ].join("\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = `retainiq-${band}-risk.csv`;
    link.click();
    URL.revokeObjectURL(link.href);
    toast("Customer list exported");
  };

  return (
    <>
      <PageHead
        eyebrow="Customer book"
        title="Prioritise the next call"
        sub="Every customer is scored by the deployed model. Switch bands, search the book and open a customer for SHAP drivers and a retention playbook."
        actions={
          <button className="btn ghost small" onClick={exportCsv}>
            <Download size={15} /> Export CSV
          </button>
        }
      />

      <div className="toolbar">
        <div className="filters">
          <div className="tabs">
            {BANDS.map((item) => (
              <button
                className={`tab ${band === item.id ? "active" : ""}`}
                key={item.id}
                onClick={() => setBand(item.id)}
              >
                {item.label}
              </button>
            ))}
          </div>
          <div className="search">
            <Search size={14} />
            <input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search customer, contract, driver…"
            />
          </div>
        </div>
        <span className="muted">
          {fmtInt(filtered.length)} of {fmtInt(totalMatching)} {band}-risk customers
        </span>
      </div>

      <article className="card">
        {loading ? (
          <div className="empty-state">
            <div className="loader-ring" style={{ margin: "0 auto 14px" }} />
            <p>Loading scored customers…</p>
          </div>
        ) : error ? (
          <EmptyState title="Could not load customers" text={error} />
        ) : (
          <>
            <HighRiskTable customers={pageRows} onOpen={openCustomer} />
            <div className="pagination">
              <span>
                Showing {filtered.length ? start + 1 : 0}–
                {Math.min(start + pageSize, filtered.length)} of {fmtInt(filtered.length)}
              </span>
              <div className="pager">
                <button disabled={currentPage <= 1} onClick={() => setPage(currentPage - 1)}>
                  ‹
                </button>
                {pageNumbers.map((number) => (
                  <button
                    key={number}
                    className={number === currentPage ? "active" : ""}
                    onClick={() => setPage(number)}
                  >
                    {number}
                  </button>
                ))}
                <button disabled={currentPage >= pages} onClick={() => setPage(currentPage + 1)}>
                  ›
                </button>
              </div>
            </div>
          </>
        )}
      </article>
    </>
  );
}
