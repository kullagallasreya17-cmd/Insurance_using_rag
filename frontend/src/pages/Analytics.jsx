import { useEffect, useMemo, useState } from "react";
import api from "../api";
import PortalLayout from "../components/PortalLayout";

function Analytics() {
  const [analytics, setAnalytics] = useState(null);

  useEffect(() => {
    api.get("/analytics").then((response) => setAnalytics(response.data));
  }, []);

  const chartEntries = (values) => Object.entries(values || {}).map(([label, count]) => ({ label, count }));

  const topQuestions = useMemo(() => analytics?.most_asked_questions || [], [analytics]);

  return (
    <PortalLayout
      title="Analytics"
      subtitle="Operational visibility into ingress, indexing, and claim activity across the microservices stack."
    >
      {!analytics && <div className="enterprise-card">Loading analytics...</div>}
      {analytics && (
        <>
          <div className="enterprise-grid">
            <article className="enterprise-card">
              <h3>Documents Uploaded</h3>
              <span className="metric-value">{analytics.totals.documents}</span>
            </article>
            <article className="enterprise-card">
              <h3>Avg Indexing Time</h3>
              <span className="metric-value">{analytics.operational_metrics?.avg_indexing_time_seconds ?? 0}s</span>
            </article>
            <article className="enterprise-card">
              <h3>Avg Chunks / Doc</h3>
              <span className="metric-value">{analytics.operational_metrics?.avg_chunks_per_document ?? 0}</span>
            </article>
            <article className="enterprise-card">
              <h3>Claim Analysis</h3>
              <span className="metric-value">{analytics.totals.claims}</span>
            </article>
          </div>

          <div className="enterprise-grid">
            <article className="enterprise-card">
              <h3>Documents by Category</h3>
              {chartEntries(analytics.documents_by_category).map((item) => (
                <div key={item.label} style={{ marginBottom: 12 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
                    <span>{item.label}</span>
                    <strong>{item.count}</strong>
                  </div>
                  <div style={{ height: 8, background: "#e2e8f0", borderRadius: 999 }}>
                    <div style={{ width: `${Math.min(100, item.count * 12)}%`, height: "100%", background: "#2563eb", borderRadius: 999 }} />
                  </div>
                </div>
              ))}
            </article>

            <article className="enterprise-card">
              <h3>Documents by Type</h3>
              {chartEntries(analytics.documents_by_type).map((item) => (
                <div key={item.label} style={{ marginBottom: 12 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
                    <span>{item.label}</span>
                    <strong>{item.count}</strong>
                  </div>
                  <div style={{ height: 8, background: "#e2e8f0", borderRadius: 999 }}>
                    <div style={{ width: `${Math.min(100, item.count * 12)}%`, height: "100%", background: "#10b981", borderRadius: 999 }} />
                  </div>
                </div>
              ))}
            </article>

            <article className="enterprise-card">
              <h3>Claims by Decision</h3>
              {chartEntries(analytics.claims_by_decision).map((item) => (
                <div key={item.label} style={{ marginBottom: 12 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
                    <span>{item.label}</span>
                    <strong>{item.count}</strong>
                  </div>
                  <div style={{ height: 8, background: "#e2e8f0", borderRadius: 999 }}>
                    <div style={{ width: `${Math.min(100, item.count * 12)}%`, height: "100%", background: "#f59e0b", borderRadius: 999 }} />
                  </div>
                </div>
              ))}
            </article>
          </div>

          <div className="enterprise-grid">
            <article className="enterprise-card">
              <h3>RAG Throughput</h3>
              <p><strong>{analytics.operational_metrics?.throughput_docs_per_minute ?? 0}</strong> docs/minute</p>
              <p><strong>{analytics.operational_metrics?.total_processing_time_seconds ?? 0}</strong> total processing seconds</p>
            </article>
            <article className="enterprise-card">
              <h3>Most Asked Questions</h3>
              <ul>
                {topQuestions.length > 0 ? (
                  topQuestions.map((item) => (
                    <li key={item.question}>
                      {item.question} {item.count ? `(${item.count})` : ""}
                    </li>
                  ))
                ) : (
                  <li>No live questions yet.</li>
                )}
              </ul>
            </article>
          </div>
        </>
      )}
    </PortalLayout>
  );
}

export default Analytics;
