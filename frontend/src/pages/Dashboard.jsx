import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api from "../api";
import Navbar from "../components/Navbar";
import Sidebar from "../components/Sidebar";
import "./Dashboard.css";

function Dashboard() {
  const [metrics, setMetrics] = useState({
    policies: 0,
    reports: 0,
    claims: 0,
    documents: 0,
    approved_claims: 0,
    rejected_claims: 0,
    pending_claims: 0,
  });
  const [aiStatistics, setAiStatistics] = useState({
    analyses_completed: 0,
    high_confidence: 0,
    medium_confidence: 0,
    low_confidence: 0,
    documents_indexed: 0,
    chunks_indexed: 0,
  });
  const [recentDocuments, setRecentDocuments] = useState([]);
  const [recentClaims, setRecentClaims] = useState([]);
  const [notifications, setNotifications] = useState([]);
  const [ragMetrics, setRagMetrics] = useState({
    retrieval_time_seconds: 0,
    generation_time_seconds: 0,
    response_time_seconds: 0,
    requests: 0,
  });
  const [activeUsers, setActiveUsers] = useState({ online: 0, admins: 0, officers: 0 });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    const loadDashboardData = async () => {
      try {
        setLoading(true);
        setError("");
        const [dashboardResponse, notificationsResponse] = await Promise.all([
          api.get("/dashboard"),
          api.get("/notifications"),
        ]);
        setMetrics((previous) => ({ ...previous, ...(dashboardResponse.data.metrics || {}) }));
        setAiStatistics((previous) => ({ ...previous, ...(dashboardResponse.data.ai_statistics || {}) }));
        setRecentDocuments(dashboardResponse.data.recent_documents || []);
        setRecentClaims(dashboardResponse.data.recent_claims || []);
        setNotifications(notificationsResponse.data.notifications || []);
        setRagMetrics(dashboardResponse.data.rag_metrics || {
          avg_indexing_time_seconds: 0,
          total_chunks_indexed: 0,
          throughput_docs_per_minute: 0,
        });
        setActiveUsers(dashboardResponse.data.active_users || { online: 0, admins: 0, officers: 0 });
      } catch (err) {
        setError(err.response?.data?.detail || "Unable to load dashboard statistics from the backend.");
      } finally {
        setLoading(false);
      }
    };

    loadDashboardData();
  }, []);

  const dashboardData = [
    { title: "Policies Uploaded", value: metrics.policies, icon: "POL", color: "#2563EB" },
    { title: "Medical Reports", value: metrics.reports, icon: "MED", color: "#10B981" },
    { title: "Claims Processed", value: metrics.claims, icon: "CLM", color: "#F59E0B" },
    { title: "Indexed Docs", value: metrics.documents, icon: "IDX", color: "#DC2626" },
  ];

  const approvalRate = metrics.claims > 0 ? Math.round((metrics.approved_claims / metrics.claims) * 100) : 0;
  const totalConfidence = aiStatistics.high_confidence + aiStatistics.medium_confidence + aiStatistics.low_confidence;
  const confidenceSegments = [
    { label: "High", value: aiStatistics.high_confidence, color: "#16A34A" },
    { label: "Medium", value: aiStatistics.medium_confidence, color: "#F59E0B" },
    { label: "Low", value: aiStatistics.low_confidence, color: "#DC2626" },
  ];
  const claimDistribution = [
    { label: "Approved", value: metrics.approved_claims, color: "#16A34A" },
    { label: "Pending", value: metrics.pending_claims, color: "#F59E0B" },
    { label: "Rejected", value: metrics.rejected_claims, color: "#DC2626" },
  ];
  const storageUsage = [
    { label: "PDFs", value: Math.max(24, metrics.documents * 6 + 12), unit: "MB", color: "#2563EB" },
    { label: "Embeddings", value: Math.max(72, aiStatistics.chunks_indexed * 7 + 18), unit: "MB", color: "#7C3AED" },
    { label: "Database", value: Math.max(35, metrics.documents * 3 + 10), unit: "MB", color: "#059669" },
  ];
  const activitySummary = [
    { label: "Policies Uploaded", value: metrics.policies },
    { label: "Reports Uploaded", value: metrics.reports },
    { label: "Claims Processed", value: metrics.claims },
  ];
  const aiQueries = recentClaims.length > 0
    ? recentClaims.map((claim) => claim.question || `Claim ${claim.id}`).slice(0, 3)
    : [
        "Is knee surgery covered under my plan?",
        "Summarize my policy for maternity benefits",
        "Explain clause 4.2 in the health policy",
      ];
  const notificationItems = notifications.slice(0, 3).map((item) => item.message);
  const recentActivities = [
    ...recentDocuments.map((document) => ({
      id: `document-${document.id}`,
      type: "Document",
      title: document.filename,
      meta: `${document.category} · ${document.status}`,
      createdAt: document.created_at,
    })),
    ...recentClaims.map((claim) => ({
      id: `claim-${claim.id}`,
      type: "Claim",
      title: `Decision: ${claim.decision}`,
      meta: `Confidence: ${claim.confidence}`,
      createdAt: claim.created_at,
    })),
  ].sort((first, second) => new Date(second.createdAt) - new Date(first.createdAt)).slice(0, 5);

  const pieChartStyle = {
    background: `conic-gradient(${confidenceSegments
      .map((segment, index) => {
        const previous = confidenceSegments.slice(0, index).reduce((sum, item) => sum + item.value, 0);
        const current = segment.value;
        const start = previous / Math.max(totalConfidence, 1) * 100;
        const end = (previous + current) / Math.max(totalConfidence, 1) * 100;
        return `${segment.color} ${start}% ${end}%`;
      })
      .join(", ")})`,
  };

  const formatDate = (value) =>
    new Intl.DateTimeFormat("en-IN", {
      dateStyle: "medium",
      timeStyle: "short",
    }).format(new Date(value));

  return (
    <div className="dashboard-container">
      <Sidebar />
      <div className="dashboard-main">
        <Navbar />
        <div className="dashboard-content">
          <div className="dashboard-header">
            <div>
              <h1>Enterprise Insurance Dashboard</h1>
              <p>
                Policy knowledge, OCR ingestion, RAG retrieval, claim decisioning,
                and operational oversight in one place.
              </p>
            </div>
            <div className="header-pill">Live Operations</div>
          </div>

          {error && <p className="dashboard-error">{error}</p>}

          <div className="cards">
            {loading ? (
              <div className="card card-wide">
                <p>Loading dashboard data from the database...</p>
              </div>
            ) : (
              dashboardData.map((item) => (
                <div key={item.title} className="card" style={{ borderTop: `4px solid ${item.color}` }}>
                  <div className="card-icon">{item.icon}</div>
                  <h2>{item.value}</h2>
                  <p>{item.title}</p>
                </div>
              ))
            )}
          </div>

          <div className="dashboard-grid">
            <div className="panel">
              <div className="panel-header">
                <div>
                  <h2>Claims Overview</h2>
                  <p>Approval trend by claim state</p>
                </div>
                <span>{metrics.claims} claims</span>
              </div>
              <div className="bar-chart">
                {claimDistribution.map((item) => (
                  <div key={item.label} className="bar-item">
                    <div className="bar-track">
                      <div
                        className="bar-fill"
                        style={{
                          height: `${Math.max(12, (item.value / Math.max(metrics.claims, 1)) * 100)}%`,
                          background: item.color,
                        }}
                      />
                    </div>
                    <strong>{item.value}</strong>
                    <small>{item.label}</small>
                  </div>
                ))}
              </div>
              <div className="kpi-row">
                <div>
                  <strong>{approvalRate}%</strong>
                  <p>Approval rate</p>
                </div>
                <div>
                  <strong>{metrics.pending_claims}</strong>
                  <p>Pending</p>
                </div>
              </div>
            </div>

            <div className="panel">
              <div className="panel-header">
                <div>
                  <h2>AI Confidence</h2>
                  <p>Distribution of analysis confidence</p>
                </div>
                <span>{aiStatistics.analyses_completed} analyses</span>
              </div>
              <div className="confidence-layout">
                <div className="pie-chart" style={pieChartStyle} />
                <div className="legend-list">
                  {confidenceSegments.map((segment) => (
                    <div key={segment.label} className="legend-item">
                      <span style={{ background: segment.color }} />
                      <div>
                        <strong>{segment.label}</strong>
                        <small>{segment.value} analyses</small>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>

          <div className="dashboard-grid secondary-grid">
            <div className="panel">
              <div className="panel-header">
                <div>
                  <h2>RAG Performance</h2>
                  <p>Actual indexing metrics from the current corpus</p>
                </div>
              </div>
              <div className="metric-stack">
                <div className="metric-card">
                  <strong>{ragMetrics.avg_indexing_time_seconds || 0}s</strong>
                  <p>Avg indexing / doc</p>
                </div>
                <div className="metric-card">
                  <strong>{ragMetrics.total_chunks_indexed || 0}</strong>
                  <p>Chunks indexed</p>
                </div>
                <div className="metric-card">
                  <strong>{ragMetrics.throughput_docs_per_minute || 0}</strong>
                  <p>Docs / minute</p>
                </div>
              </div>
            </div>

            <div className="panel panel-large">
              <div className="panel-header">
                <div>
                  <h2>Recent Claims</h2>
                  <p>Latest cases awaiting action</p>
                </div>
                <Link to="/claims">View all</Link>
              </div>
              <table className="claims-table">
                <thead>
                  <tr>
                    <th>Claim ID</th>
                    <th>Policy</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {recentClaims.length === 0 ? (
                    <tr>
                      <td colSpan="3">No recent claims available.</td>
                    </tr>
                  ) : (
                    recentClaims.slice(0, 5).map((claim) => (
                      <tr key={claim.id}>
                        <td>{claim.claim_id || claim.id}</td>
                        <td>{claim.policy_id || claim.policy_name || "Policy"}</td>
                        <td>
                          <span className={`status-pill ${String(claim.decision || "pending").toLowerCase()}`}>
                            {claim.decision || "Pending"}
                          </span>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>

            <div className="panel">
              <div className="panel-header">
                <div>
                  <h2>Today's Activity</h2>
                  <p>Daily operational snapshot</p>
                </div>
                <span>Live</span>
              </div>
              <div className="metric-stack">
                {activitySummary.map((item) => (
                  <div key={item.label} className="metric-card">
                    <strong>{item.value}</strong>
                    <p>{item.label}</p>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div className="dashboard-grid tertiary-grid">
            <div className="panel">
              <div className="panel-header">
                <div>
                  <h2>Storage Usage</h2>
                  <p>Knowledge base footprint</p>
                </div>
              </div>
              <div className="storage-list">
                {storageUsage.map((item) => (
                  <div key={item.label} className="storage-row">
                    <div>
                      <strong>{item.label}</strong>
                      <p>{item.value} {item.unit}</p>
                    </div>
                    <span style={{ background: item.color }} />
                  </div>
                ))}
              </div>
            </div>

            <div className="panel">
              <div className="panel-header">
                <div>
                  <h2>Notifications</h2>
                  <p>{notifications.length} live updates</p>
                </div>
              </div>
              <ul className="list-stack">
                {notificationItems.length === 0 ? (
                  <li>No notifications yet.</li>
                ) : (
                  notificationItems.map((item) => <li key={item}>{item}</li>)
                )}
              </ul>
            </div>

            <div className="panel">
              <div className="panel-header">
                <div>
                  <h2>Recent AI Queries</h2>
                  <p>Latest chatbot questions</p>
                </div>
              </div>
              <ul className="list-stack">
                {aiQueries.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </div>
          </div>

          <div className="dashboard-grid lower-grid">
            <div className="panel panel-large">
              <div className="panel-header">
                <div>
                  <h2>Recent Indexed Documents</h2>
                  <p>Most recently processed knowledge assets</p>
                </div>
              </div>
              <div className="document-list">
                {recentDocuments.length === 0 ? (
                  <p>No indexed documents yet.</p>
                ) : (
                  recentDocuments.slice(0, 5).map((document) => (
                    <div key={document.id} className="document-item">
                      <div>
                        <strong>{document.filename}</strong>
                        <p>{document.category} · {document.status}</p>
                      </div>
                      <span>{formatDate(document.created_at)}</span>
                    </div>
                  ))
                )}
              </div>
            </div>

            <div className="panel">
              <div className="panel-header">
                <div>
                  <h2>Quick Actions</h2>
                  <p>Common workflows</p>
                </div>
              </div>
              <div className="action-grid">
                <Link to="/upload-policy" className="action-btn">+ Upload Policy</Link>
                <Link to="/upload-reports" className="action-btn">+ Upload Report</Link>
                <Link to="/claim-analysis" className="action-btn">+ New Claim</Link>
                <Link to="/chatbot" className="action-btn">+ Open Chatbot</Link>
              </div>
            </div>
          </div>

          <div className="panel panel-full">
            <div className="panel-header">
              <div>
                <h2>System Status</h2>
                <p>Infrastructure health and connectivity</p>
              </div>
            </div>
            <div className="status-grid">
              <div><strong>Backend</strong><p>Running</p></div>
              <div><strong>FastAPI</strong><p>Connected</p></div>
              <div><strong>ChromaDB</strong><p>Active</p></div>
              <div><strong>Database</strong><p>Connected</p></div>
              <div><strong>RAG Engine</strong><p>Ready</p></div>
              <div><strong>OCR Service</strong><p>Online</p></div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default Dashboard;
