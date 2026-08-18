import { useEffect, useMemo, useState } from "react";
import api from "../api";
import PortalLayout from "../components/PortalLayout";

const FILTER_OPTIONS = ["All", "Health", "Vehicle", "Life", "Home", "Travel", "Accident", "Critical Illness", "Property", "FAQ", "Claim Procedure", "Others"];
const ICONS = {
  health: "🏥",
  vehicle: "🚗",
  life: "❤️",
  home: "🏠",
  travel: "✈️",
  accident: "🛡️",
  critical: "💙",
  property: "🏢",
  faq: "📄",
  claim: "📋",
};

function Policies() {
  const [policies, setPolicies] = useState([]);
  const [searchText, setSearchText] = useState("");
  const [activeFilter, setActiveFilter] = useState("All");

  useEffect(() => {
    api.get("/policies").then((response) => setPolicies(response.data.policies || []));
  }, []);

  const filteredPolicies = useMemo(() => {
    const normalized = searchText.toLowerCase().trim();

    return policies.filter((policy) => {
      const matchesSearch = !normalized || [policy.name, policy.category, policy.uploaded_by].join(" ").toLowerCase().includes(normalized);
      const matchesFilter = (() => {
        if (activeFilter === "All") return true;
        if (activeFilter === "Health") return policy.category.includes("health");
        if (activeFilter === "Vehicle") return policy.category.includes("vehicle");
        if (activeFilter === "Life") return policy.category.includes("life");
        if (activeFilter === "Home") return policy.category.includes("home");
        if (activeFilter === "Travel") return policy.category.includes("travel");
        if (activeFilter === "Accident") return policy.category.includes("accident");
        if (activeFilter === "Critical Illness") return policy.category.includes("critical");
        if (activeFilter === "Property") return policy.category.includes("property");
        if (activeFilter === "FAQ") return policy.category.includes("faq");
        if (activeFilter === "Claim Procedure") return policy.category.includes("claim");
        if (activeFilter === "Others") return !["health", "vehicle", "life", "home", "travel", "accident", "critical", "property", "faq", "claim"].some((k) => policy.category.includes(k));
        return true;
      })();

      return matchesSearch && matchesFilter;
    });
  }, [policies, searchText, activeFilter]);

  const getPolicyIcon = (category) => {
    const normalized = String(category || "").toLowerCase();
    const key = normalized.includes("vehicle") ? "vehicle"
      : normalized.includes("health") ? "health"
      : normalized.includes("life") ? "life"
      : normalized.includes("home") ? "home"
      : normalized.includes("travel") ? "travel"
      : normalized.includes("accident") ? "accident"
      : normalized.includes("critical") ? "critical"
      : normalized.includes("property") ? "property"
      : normalized.includes("claim") ? "claim"
      : "faq";
    return ICONS[key] || "📘";
  };

  const viewPolicy = async (id, filename) => {
    const newTab = window.open("", "_blank");
    if (!newTab) {
      alert("Please allow popups to view policies.");
      return;
    }

    try {
      const response = await api.get(`/document/${id}/download`, { responseType: "blob" });
      const blob = new Blob([response.data], { type: response.headers["content-type"] || "application/octet-stream" });
      const url = window.URL.createObjectURL(blob);
      newTab.location.href = url;
      setTimeout(() => window.URL.revokeObjectURL(url), 60 * 1000);
    } catch (err) {
      console.error("Failed to open policy", err);
      newTab.close();
      alert("Unable to open policy. Try downloading instead.");
    }
  };

  const downloadPolicy = async (id, filename) => {
    try {
      const response = await api.get(`/document/${id}/download`, { responseType: "blob" });
      const blob = new Blob([response.data], { type: response.headers["content-type"] || "application/octet-stream" });
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = filename || "policy";
      document.body.appendChild(link);
      link.click();
      link.remove();
      setTimeout(() => window.URL.revokeObjectURL(url), 60 * 1000);
    } catch (err) {
      console.error("Failed to download policy", err);
      alert("Download failed. Please try again.");
    }
  };

  const openChatbot = () => {
    window.location.href = "/chatbot";
  };

  const reindexPolicy = async (id) => {
    if (!window.confirm("Re-index this policy now?")) return;
    try {
      await api.post(`/document/${id}/reindex`);
      // refresh list
      const resp = await api.get("/policies");
      setPolicies(resp.data.policies || []);
      alert("Re-index started/completed.");
    } catch (err) {
      console.error("Re-index failed", err);
      alert("Failed to re-index policy.");
    }
  };

  const regenerateSummary = async (id) => {
    try {
      await api.post(`/document/${id}/summary`);
      const resp = await api.get("/policies");
      setPolicies(resp.data.policies || []);
    } catch (err) {
      console.error("Summary generation failed", err);
      alert("Failed to generate policy summary.");
    }
  };

  const deletePolicy = async (id) => {
    if (!window.confirm("Delete this policy? This action cannot be undone.")) return;
    try {
      await api.delete(`/document/${id}`);
      const resp = await api.get("/policies");
      setPolicies(resp.data.policies || []);
    } catch (err) {
      console.error("Delete failed", err);
      alert("Failed to delete policy.");
    }
  };

  const formatDate = (dateValue) => {
    if (!dateValue) return "N/A";
    return new Date(dateValue).toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" });
  };

  return (
    <PortalLayout
      title="Policy Library"
      subtitle="Policy documents are separated here for coverage browsing, policy reviews, and AI-assisted claim support."
    >
      <div className="card-actions" style={{ marginBottom: "18px" }}>
        <input
          type="text"
          placeholder="Search Policies..."
          value={searchText}
          onChange={(event) => setSearchText(event.target.value)}
          style={{ minWidth: 260, padding: "10px 12px", borderRadius: 6, border: "1px solid #cbd5e1" }}
        />

        {FILTER_OPTIONS.map((option) => (
          <button
            key={option}
            className={`table-action-button ${activeFilter === option ? "" : "secondary"}`}
            onClick={() => setActiveFilter(option)}
          >
            {option}
          </button>
        ))}
      </div>

      <div className="enterprise-grid">
        {filteredPolicies.map((policy) => (
          <article className="enterprise-card" key={policy.id}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "12px" }}>
              <span style={{ fontSize: 28 }}>{getPolicyIcon(policy.category)}</span>
              <span className="status-pill">{policy.status}</span>
            </div>
            <h3>{policy.name}</h3>
            <p><strong>Category</strong><br />{policy.category}</p>
            <p><strong>Coverage</strong><br />₹{Math.max(100000, policy.pages * 100000)}</p>
            <p><strong>Pages</strong><br />{policy.pages || 0}</p>
            <p><strong>Chunks</strong><br />{policy.chunks || 0}</p>
            <p><strong>Version</strong><br />{policy.version || 1}</p>
            <p><strong>Uploaded</strong><br />{formatDate(policy.created_at)}</p>
            <p><strong>Indexed</strong><br />{policy.status}</p>
            <p>
              <strong>AI Summary</strong><br />
              {policy.summary_status === "generating"
                ? "Generating summary..."
                : policy.policy_summary || "Summary will appear after indexing completes."}
            </p>
            <div className="card-actions" style={{ marginTop: "16px", display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
              <button className="table-action-button" onClick={() => viewPolicy(policy.id, policy.name)}>View</button>
              <button className="table-action-button secondary" onClick={() => downloadPolicy(policy.id, policy.name)}>Download</button>
              <button className="table-action-button secondary" onClick={() => reindexPolicy(policy.id)}>🔄 Re-index</button>
              <button className="table-action-button secondary" onClick={() => deletePolicy(policy.id)}>🗑 Delete</button>
              <button className="table-action-button secondary" onClick={openChatbot}>Ask AI</button>
            </div>
          </article>
        ))}

        {filteredPolicies.length === 0 && (
          <article className="enterprise-card">
            <h3>No Policies</h3>
            <p>Upload an insurance policy to populate this library view.</p>
          </article>
        )}
      </div>
    </PortalLayout>
  );
}

export default Policies;
