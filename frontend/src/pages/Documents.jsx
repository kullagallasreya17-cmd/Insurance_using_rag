import { useEffect, useMemo, useState } from "react";
import api from "../api";
import PortalLayout from "../components/PortalLayout";

const FILTER_OPTIONS = ["All", "Policy", "Medical", "FAQ", "Claims"];

function Documents() {
  const [documents, setDocuments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchText, setSearchText] = useState("");
  const [activeFilter, setActiveFilter] = useState("All");

  const loadDocuments = () => {
    setLoading(true);
    api
      .get("/documents")
      .then((response) => setDocuments(response.data.documents || []))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    loadDocuments();
  }, []);

  const stats = useMemo(() => {
    const totalDocuments = documents.length;
    const indexed = documents.filter((document) => (document.status || "").toLowerCase() === "indexed").length;
    const pending = documents.filter((document) => (document.status || "").toLowerCase() === "pending").length;
    const failed = documents.filter((document) => (document.status || "").toLowerCase() === "failed").length;

    return { totalDocuments, indexed, pending, failed };
  }, [documents]);

  const filteredDocuments = useMemo(() => {
    const normalized = searchText.toLowerCase().trim();

    return documents.filter((document) => {
      const matchesSearch =
        !normalized ||
        [document.filename, document.document_type, document.category, document.uploaded_by]
          .join(" ")
          .toLowerCase()
          .includes(normalized);

      const matchesFilter = (() => {
        if (activeFilter === "All") return true;
        if (activeFilter === "Policy") return document.document_type === "policy" || document.category.includes("policy");
        if (activeFilter === "Medical") return document.category.includes("medical") || document.document_type.includes("report") || document.category.includes("hospital") || document.category.includes("prescription") || document.category.includes("lab");
        if (activeFilter === "FAQ") return document.category.includes("faq") || document.category.includes("terms");
        if (activeFilter === "Claims") return document.category.includes("claim") || document.document_type.includes("claim");
        return true;
      })();

      return matchesSearch && matchesFilter;
    });
  }, [documents, searchText, activeFilter]);

  const deleteDocument = async (id) => {
    if (!window.confirm("Are you sure you want to delete this document? This cannot be undone.")) return;
    try {
      await api.delete(`/document/${id}`);
      loadDocuments();
    } catch (err) {
      console.error("Delete failed", err);
      alert("Failed to delete document. See console for details.");
    }
  };

  const reindexDocument = async (id) => {
    if (!window.confirm("Re-index this document now? This may take a moment.")) return;
    try {
      await api.post(`/document/${id}/reindex`);
      loadDocuments();
      alert("Re-index started/completed.");
    } catch (err) {
      console.error("Re-index failed", err);
      alert("Failed to re-index. See console for details.");
    }
  };

  const viewDocument = async (id, filename) => {
    const newTab = window.open("", "_blank");
    if (!newTab) {
      alert("Please allow popups to view documents.");
      return;
    }

    try {
      const response = await api.get(`/document/${id}/download`, { responseType: "blob" });
      const blob = new Blob([response.data], { type: response.headers["content-type"] || "application/octet-stream" });
      const url = window.URL.createObjectURL(blob);
      newTab.location.href = url;
      setTimeout(() => window.URL.revokeObjectURL(url), 60 * 1000);
    } catch (err) {
      console.error("Failed to open document", err);
      newTab.close();
      alert("Unable to open document. Please try downloading instead.");
    }
  };

  const downloadDocument = async (id, filename) => {
    try {
      const response = await api.get(`/document/${id}/download`, { responseType: "blob" });
      const blob = new Blob([response.data], { type: response.headers["content-type"] || "application/octet-stream" });
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = filename || "document";
      document.body.appendChild(link);
      link.click();
      link.remove();
      setTimeout(() => window.URL.revokeObjectURL(url), 60 * 1000);
    } catch (err) {
      console.error("Failed to download document", err);
      alert("Download failed. Please try again.");
    }
  };

  const formatDate = (dateValue) => {
    if (!dateValue) return "N/A";
    return new Date(dateValue).toLocaleString();
  };

  return (
    <PortalLayout
      title="Documents"
      subtitle="Administrator document management for uploaded policies, reports, FAQ assets, and claim evidence."
    >
      <div className="enterprise-grid">
        <article className="enterprise-card">
          <h3>Total Documents</h3>
          <span className="metric-value">{stats.totalDocuments}</span>
        </article>
        <article className="enterprise-card">
          <h3>Indexed</h3>
          <span className="metric-value">{stats.indexed}</span>
        </article>
        <article className="enterprise-card">
          <h3>Pending</h3>
          <span className="metric-value">{stats.pending}</span>
        </article>
        <article className="enterprise-card">
          <h3>Failed</h3>
          <span className="metric-value">{stats.failed}</span>
        </article>
      </div>

      <div className="card-actions" style={{ marginBottom: "18px" }}>
        <input
          type="text"
          placeholder="Search documents..."
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

      <table className="enterprise-table">
        <thead>
          <tr>
            <th>File</th>
            <th>Type</th>
            <th>Category</th>
            <th>Pages</th>
            <th>Chunks</th>
            <th>Version</th>
            <th>Uploaded By</th>
            <th>Upload Date</th>
            <th>Status</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {loading && (
            <tr>
              <td colSpan="10">Loading documents...</td>
            </tr>
          )}
          {!loading && filteredDocuments.length === 0 && (
            <tr>
              <td colSpan="10">No matching documents found.</td>
            </tr>
          )}
          {filteredDocuments.map((document) => (
            <tr key={document.id}>
              <td>{document.filename}</td>
              <td>{document.document_type}</td>
              <td>{document.category}</td>
              <td>{document.pages || 0}</td>
              <td>{document.chunks || 0}</td>
              <td>{document.version || 1}</td>
              <td>{document.uploaded_by}</td>
              <td>{formatDate(document.created_at)}</td>
              <td><span className="status-pill">{document.status || "indexed"}</span></td>
              <td>
                <div className="table-actions" style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                    <button className="table-action-button" onClick={() => viewDocument(document.id, document.filename)}>👁 View</button>
                    <button className="table-action-button secondary" onClick={() => downloadDocument(document.id, document.filename)}>⬇ Download</button>
                    <button className="table-action-button secondary" onClick={() => reindexDocument(document.id)}>🔄 Re-index</button>
                    <button className="table-action-button secondary" onClick={() => deleteDocument(document.id)}>🗑 Delete</button>
                  </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </PortalLayout>
  );
}

export default Documents;
