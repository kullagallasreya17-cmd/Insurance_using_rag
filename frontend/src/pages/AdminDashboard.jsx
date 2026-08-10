import { useEffect, useState } from "react";
import api from "../api";
import PortalLayout from "../components/PortalLayout";

const DEFAULT_PERMISSION_MAP = {
  admin: ["dashboard:read", "users:read", "audit:read", "security:read"],
  analyst: ["dashboard:read", "claims:read", "documents:read", "chat:ask"],
  agent: ["documents:read", "chat:ask", "claims:analyze"],
  auditor: ["dashboard:read", "claims:read", "audit:read", "reports:read"],
};

function AdminDashboard() {
  const [overview, setOverview] = useState(null);
  const [message, setMessage] = useState("");
  const [modal, setModal] = useState(null);

  const roleClassMap = {
    admin: "role-badge role-admin",
    analyst: "role-badge role-analyst",
    agent: "role-badge role-agent",
    auditor: "role-badge role-auditor",
  };

  const openModal = (title, content) => {
    setModal({ title, content });
  };

  const handleViewOnlyAction = (label) => {
    setMessage("The Admin Dashboard is currently view-only in this version. Direct user management actions are planned for a future release.");
    openModal(label, [
      "This dashboard currently exposes read-only operational visibility.",
      "Direct user-management actions such as editing roles or deactivating accounts are intentionally deferred for the next release.",
    ]);
  };

  const getUserPermissions = (role) => DEFAULT_PERMISSION_MAP[role?.toLowerCase()] || DEFAULT_PERMISSION_MAP.agent;

  useEffect(() => {
    api
      .get("/admin/overview")
      .then((response) => setOverview(response.data))
      .catch((error) => setMessage(error.response?.data?.detail || "Unable to load admin dashboard."));
  }, []);

  return (
    <PortalLayout title="Admin Dashboard" subtitle="Users, roles, and service readiness overview.">
      {message && <div className="enterprise-card info-banner">{message}</div>}
      {overview && (
        <>
          <div className="enterprise-grid">
            {overview.service_health.map((service) => (
              <article className="enterprise-card service-card" key={service.service}>
                <div className="service-card-header">
                  <h3>{service.service}</h3>
                  <span className={`service-dot ${service.status.toLowerCase().includes("running") ? "online" : "pending"}`} />
                </div>
                <p>{service.status}</p>
                <div className="card-actions">
                  <button
                    type="button"
                    className="enterprise-button"
                    onClick={() => openModal(`${service.service} overview`, [
                      `Current status: ${service.status}`,
                      "This card reflects the operational readiness and health of a core platform service in the insurance workflow.",
                    ])}
                  >
                    View details
                  </button>
                  <button
                    type="button"
                    className="secondary-button"
                    onClick={() => openModal(`${service.service} access log`, [
                      "2026-08-03 09:10 — Service heartbeat received",
                      "2026-08-03 09:15 — Document sync completed",
                      "2026-08-03 09:27 — Vector retrieval healthy",
                    ])}
                  >
                    Access log
                  </button>
                </div>
              </article>
            ))}
          </div>

          <div className="enterprise-card" style={{ marginTop: "24px" }}>
            <h3>Recent Audit Activity</h3>
            <table className="enterprise-table">
              <thead>
                <tr>
                  <th>Actor</th>
                  <th>Role</th>
                  <th>Action</th>
                  <th>Details</th>
                  <th>Timestamp</th>
                </tr>
              </thead>
              <tbody>
                {(overview.audit_logs || []).map((entry) => (
                  <tr key={entry.id}>
                    <td>{entry.actor}</td>
                    <td>{entry.actor_role}</td>
                    <td>{entry.action}</td>
                    <td>{entry.details}</td>
                    <td>{new Date(entry.created_at).toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <table className="enterprise-table" style={{ marginTop: "24px" }}>
            <thead>
              <tr>
                <th>User</th>
                <th>Full Name</th>
                <th>Role</th>
                <th>Created</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {overview.users.map((user) => (
                <tr key={user.id}>
                  <td>{user.username}</td>
                  <td>{user.full_name}</td>
                  <td>
                    <span className={roleClassMap[user.role?.toLowerCase()] || "role-badge role-agent"}>
                      {user.role}
                    </span>
                  </td>
                  <td>{new Date(user.created_at).toLocaleString()}</td>
                  <td>
                    <div className="table-actions">
                      <button
                        type="button"
                        className="table-action-button"
                        onClick={() => openModal(`${user.full_name} profile`, [
                          `Username: ${user.username}`,
                          `Role: ${user.role}`,
                          `Created: ${new Date(user.created_at).toLocaleString()}`,
                          "Status: active",
                        ])}
                      >
                        View profile
                      </button>
                      <button
                        type="button"
                        className="table-action-button secondary"
                        onClick={() => openModal(`${user.full_name} permissions`, getUserPermissions(user.role))}
                      >
                        Permissions
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}

      {modal && (
        <div className="modal-backdrop" onClick={() => setModal(null)}>
          <div className="modal-card" onClick={(event) => event.stopPropagation()}>
            <div className="modal-header">
              <h3>{modal.title}</h3>
              <button type="button" className="close-button" onClick={() => setModal(null)}>×</button>
            </div>
            {Array.isArray(modal.content) ? (
              <ul className="modal-list">
                {modal.content.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            ) : (
              <p>{modal.content}</p>
            )}
          </div>
        </div>
      )}
    </PortalLayout>
  );
}

export default AdminDashboard;
