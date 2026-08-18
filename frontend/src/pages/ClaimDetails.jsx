import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import api from "../api";
import PortalLayout from "../components/PortalLayout";

function ClaimDetails() {
  const { id } = useParams();
  const [claim, setClaim] = useState(null);

  useEffect(() => {
    api.get(`/claim/${id}`).then((response) => setClaim(response.data));
  }, [id]);

  const statusClass = (decision) => {
    const value = (decision || "needs_review").toLowerCase();
    if (value === "approved") return "status-badge approved";
    if (value === "rejected") return "status-badge rejected";
    return "status-badge needs-review";
  };

  const formatDate = (dateValue) => {
    if (!dateValue) return "N/A";
    return new Date(dateValue).toLocaleString();
  };

  return (
    <PortalLayout title="Claim Details" subtitle={`Audit details for claim analysis ${id}.`}>
      {!claim && <div className="enterprise-card">Loading claim...</div>}
      {claim && (
        <div className="enterprise-card">
          <h2>Decision: <span className={statusClass(claim.decision)}>{claim.decision}</span></h2>
          <p><strong>Date:</strong> {formatDate(claim.created_at)}</p>
          <p><strong>Confidence:</strong> {claim.confidence}</p>
          <p><strong>Question:</strong> {claim.question}</p>
          <p><strong>Rationale:</strong> {claim.rationale}</p>
          <p><strong>Missing Information:</strong> {claim.missing_information || "None"}</p>
          <p><strong>Policy Document ID:</strong> {claim.policy_document_id || "Best matching policy used"}</p>
          <p><strong>Claim Evidence IDs:</strong> {(claim.claim_document_ids || []).join(", ") || "None selected"}</p>
          <p><strong>Explanation Trail:</strong> {Array.isArray(claim.explanation_trail) ? claim.explanation_trail.join(" | ") : claim.explanation_trail || "Not available"}</p>
          <p><strong>Evidence Summary:</strong> {claim.evidence_summary || "Not available"}</p>

          {claim.rag_evaluation && (
            <div>
              <h3>RAG Evaluation</h3>
              <p><strong>Grounded:</strong> {claim.rag_evaluation.grounded ? "Yes" : "Needs review"}</p>
              <p><strong>Policy Sources:</strong> {claim.rag_evaluation.policy_source_count || 0}</p>
              <p><strong>Claim Evidence Sources:</strong> {claim.rag_evaluation.claim_source_count || 0}</p>
              <p><strong>Warnings:</strong> {(claim.rag_evaluation.warnings || []).join(", ") || "None"}</p>
            </div>
          )}

          {Array.isArray(claim.sources) && claim.sources.length > 0 && (
            <div>
              <h3>Retrieved Sources</h3>
              <ul>
                {claim.sources.map((source, index) => (
                  <li key={index}>
                    <strong>{source.source || "unknown source"}</strong>
                    {source.page && <span> - page: {source.page}</span>}
                    {source.evidence_role && <span> - role: {source.evidence_role}</span>}
                    <div>{source.excerpt || "No excerpt available."}</div>
                  </li>
                ))}
              </ul>
            </div>
          )}
          <p><strong>Created By:</strong> {claim.created_by}</p>
        </div>
      )}
    </PortalLayout>
  );
}

export default ClaimDetails;
