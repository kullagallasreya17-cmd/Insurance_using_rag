import { useEffect, useMemo, useState } from "react";
import api from "../api";
import Navbar from "../components/Navbar";
import Sidebar from "../components/Sidebar";
import "./KnowledgeBase.css";

function KnowledgeBase() {
  const [documents, setDocuments] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .get("/documents")
      .then((response) => setDocuments(response.data.documents || []))
      .finally(() => setLoading(false));
  }, []);

  const knowledgeDocuments = useMemo(() => {
    return documents.filter((document) =>
      ["faq", "terms_conditions", "claim_procedure", "medical_document", "health_policy", "vehicle_policy", "life_policy"].includes(document.category)
    );
  }, [documents]);

  const summary = useMemo(() => {
    return {
      totalPolicies: documents.filter((document) => document.document_type === "policy").length,
      medicalReports: documents.filter((document) => document.category.includes("medical") || document.category.includes("report") || document.document_type !== "policy").length,
      faq: documents.filter((document) => document.category.includes("faq") || document.category.includes("terms")).length,
      claimProcedures: documents.filter((document) => document.category.includes("claim")).length,
    };
  }, [documents]);

  return (
    <div className="knowledge-page">
      <Sidebar />
      <div className="knowledge-main">
        <Navbar />
        <section className="knowledge-content">
          <h1>Knowledge Base</h1>
          <p>
            Indexed knowledge used by the RAG assistant for policy retrieval, medical support, and claim guidance.
          </p>

          <div className="enterprise-grid">
            <article className="enterprise-card">
              <h3>Total Policies</h3>
              <span className="metric-value">{summary.totalPolicies}</span>
            </article>
            <article className="enterprise-card">
              <h3>Medical Reports</h3>
              <span className="metric-value">{summary.medicalReports}</span>
            </article>
            <article className="enterprise-card">
              <h3>FAQ</h3>
              <span className="metric-value">{summary.faq}</span>
            </article>
            <article className="enterprise-card">
              <h3>Claim Procedures</h3>
              <span className="metric-value">{summary.claimProcedures}</span>
            </article>
          </div>

          <div className="knowledge-table">
            <table>
              <thead>
                <tr>
                  <th>File</th>
                  <th>Type</th>
                  <th>Category</th>
                  <th>Pages</th>
                  <th>Chunks</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {loading && (
                  <tr>
                    <td colSpan="6">Loading documents...</td>
                  </tr>
                )}
                {!loading && knowledgeDocuments.length === 0 && (
                  <tr>
                    <td colSpan="6">No supporting knowledge documents yet.</td>
                  </tr>
                )}
                {knowledgeDocuments.map((document) => (
                  <tr key={document.id}>
                    <td>{document.filename}</td>
                    <td>{document.document_type}</td>
                    <td>{document.category}</td>
                    <td>{document.pages || 0}</td>
                    <td>{document.chunks || 0}</td>
                    <td>{document.status}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </div>
  );
}

export default KnowledgeBase;
