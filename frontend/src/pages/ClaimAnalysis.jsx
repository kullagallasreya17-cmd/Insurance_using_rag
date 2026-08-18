import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api from "../api";
import { getUser } from "../auth";
import Navbar from "../components/Navbar";
import Sidebar from "../components/Sidebar";
import "./ClaimAnalysis.css";

function ClaimAnalysis() {
  const user = getUser() || {};
  const role = (user.role || "customer").toLowerCase();
  const canAnalyzeClaims = ["admin", "customer"].includes(role);
  const [question, setQuestion] = useState("");
  const [diagnosis, setDiagnosis] = useState("");
  const [hospitalName, setHospitalName] = useState("");
  const [claimAmount, setClaimAmount] = useState("");
  const [policyCategory, setPolicyCategory] = useState("health_policy");
  const [documents, setDocuments] = useState([]);
  const [selectedPolicyId, setSelectedPolicyId] = useState("");
  const [selectedClaimDocumentIds, setSelectedClaimDocumentIds] = useState([]);
  const [validationMessage, setValidationMessage] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [claims, setClaims] = useState([]);

  const fetchClaims = async () => {
    try {
      const response = await api.get("/claims");
      setClaims(response.data.claims || []);
    } catch (error) {
      console.error("Failed to load claim history", error);
    }
  };

  useEffect(() => {
    fetchClaims();
    if (canAnalyzeClaims) {
      api
        .get("/documents", { params: { limit: 200 } })
        .then((response) => setDocuments(response.data.documents || []))
        .catch((error) => console.error("Failed to load documents", error));
    }
  }, [canAnalyzeClaims]);

  const policyDocuments = documents.filter(
    (document) => document.document_type === "policy" && (!policyCategory || document.category === policyCategory)
  );
  const claimEvidenceDocuments = documents.filter((document) => document.document_type !== "policy");
  const selectedClaimDocuments = claimEvidenceDocuments.filter((document) =>
    selectedClaimDocumentIds.includes(String(document.id))
  );

  const toggleClaimDocument = (documentId) => {
    const id = String(documentId);
    setSelectedClaimDocumentIds((current) =>
      current.includes(id) ? current.filter((item) => item !== id) : [...current, id]
    );
  };

  const decisionClass = (decision) => {
    const normalized = (decision || "needs_review").toLowerCase();
    if (normalized === "approved") return "status-badge approved";
    if (normalized === "rejected") return "status-badge rejected";
    return "status-badge needs-review";
  };

  const analyzeClaim = async () => {
    if (!question.trim()) {
      setValidationMessage("Please enter question or report details.");
      return;
    }

    try {
      setValidationMessage("");
      setLoading(true);
      const response = await api.post("/claim/analyze", {
        question,
        treatment_details: question,
        diagnosis: diagnosis || "not provided",
        hospital_name: hospitalName || "not provided",
        claim_amount: claimAmount ? Number(claimAmount) : null,
        policy_category: policyCategory,
        policy_document_id: selectedPolicyId ? Number(selectedPolicyId) : null,
        claim_document_ids: selectedClaimDocumentIds.map((id) => Number(id)),
      });
      setResult(response.data);
      await fetchClaims();
    } catch (error) {
      setValidationMessage(error.response?.data?.detail || "Unable to analyze claim.");
    } finally {
      setLoading(false);
    }
  };

  const formatDate = (dateValue) => {
    if (!dateValue) return "N/A";
    return new Date(dateValue).toLocaleString();
  };

  const policyLabel = {
    health_policy: "Health Policy",
    vehicle_policy: "Vehicle Policy",
    life_policy: "Life Policy",
    home_policy: "Home Policy",
    travel_policy: "Travel Policy",
    personal_accident_policy: "Personal Accident Policy",
    critical_illness_policy: "Critical Illness Policy",
    property_policy: "Property Policy",
    other: "Others",
  }[policyCategory] || policyCategory;

  return (
    <div className="claim-page">
      <Sidebar />
      <div className="claim-main">
        <Navbar />
        <div className="claim-content">
          <h1>Claim Analysis & Claims</h1>
          <p>Generate and review structured claim decisions using policy clauses, uploaded reports, and retrieved evidence.</p>

          {canAnalyzeClaims ? (
            <>
              <div className="analysis-box">
                <div className="field-group">
                  <label className="field-label">Details / Question</label>
                  <input
                    type="text"
                    placeholder="Enter a question or description to analyze."
                    value={question}
                    onChange={(event) => setQuestion(event.target.value)}
                  />
                </div>

                <div className="field-group">
                  <label className="field-label">Diagnosis / condition</label>
                  <input
                    type="text"
                    placeholder="Example: Knee ligament tear"
                    value={diagnosis}
                    onChange={(event) => setDiagnosis(event.target.value)}
                  />
                </div>

                <div className="field-group">
                  <label className="field-label">Hospital name</label>
                  <input
                    type="text"
                    placeholder="Enter hospital or network provider"
                    value={hospitalName}
                    onChange={(event) => setHospitalName(event.target.value)}
                  />
                </div>

                <div className="field-group">
                  <label className="field-label">Claim amount (Rs.)</label>
                  <input
                    type="number"
                    placeholder="Enter claim amount"
                    value={claimAmount}
                    onChange={(event) => setClaimAmount(event.target.value)}
                  />
                </div>

                <div className="field-group">
                  <label className="field-label">Policy type</label>
                  <select value={policyCategory} onChange={(event) => setPolicyCategory(event.target.value)}>
                    <option value="health_policy">Health Policy</option>
                    <option value="vehicle_policy">Vehicle Policy</option>
                    <option value="life_policy">Life Policy</option>
                    <option value="home_policy">Home Policy</option>
                    <option value="travel_policy">Travel Policy</option>
                    <option value="personal_accident_policy">Personal Accident Policy</option>
                    <option value="critical_illness_policy">Critical Illness Policy</option>
                    <option value="property_policy">Property Policy</option>
                    <option value="other">Others</option>
                  </select>
                </div>

                <div className="field-group report-field">
                  <label className="field-label">Policy document</label>
                  <select value={selectedPolicyId} onChange={(event) => setSelectedPolicyId(event.target.value)}>
                    <option value="">Use best matching indexed policy</option>
                    {policyDocuments.map((document) => (
                      <option key={document.id} value={document.id}>
                        {document.filename}
                      </option>
                    ))}
                  </select>
                  {policyDocuments.length === 0 && (
                    <div className="selected-report">No indexed policy found for this policy type.</div>
                  )}
                </div>

                <div className="field-group evidence-field">
                  <label className="field-label">Supporting claim evidence</label>
                  <div className="evidence-picker">
                    {claimEvidenceDocuments.length === 0 && <span>No supporting documents indexed yet.</span>}
                    {claimEvidenceDocuments.map((document) => (
                      <label key={document.id} className="evidence-option">
                        <input
                          type="checkbox"
                          checked={selectedClaimDocumentIds.includes(String(document.id))}
                          onChange={() => toggleClaimDocument(document.id)}
                        />
                        <span>{document.filename}</span>
                      </label>
                    ))}
                  </div>
                </div>
              </div>

              {validationMessage && <div className="validation-message">{validationMessage}</div>}

              <button className="analyze-button" onClick={analyzeClaim} disabled={loading}>
                {loading ? "Analyzing claim..." : "Analyze Claim"}
              </button>
            </>
          ) : (
            <div className="result-card">
              <h2>Claim Audit View</h2>
              <p>Auditors can inspect claim history, retrieved sources, RAG evaluation, and explanation trails.</p>
            </div>
          )}

          {result && (
            <div className="result-card">
              <div className="result-header-row">
                <h2>Claim Decision</h2>
                <span className={decisionClass(result.decision)}>
                  {result.decision ? result.decision.toUpperCase() : "NEEDS REVIEW"}
                </span>
              </div>

              <div className="result-grid">
                <div className="result-stat"><span>Confidence</span><strong>{result.confidence || "medium"}</strong></div>
                <div className="result-stat"><span>Claim Amount</span><strong>Rs. {claimAmount || "0"}</strong></div>
                <div className="result-stat"><span>Policy Type</span><strong>{policyLabel}</strong></div>
                <div className="result-stat"><span>Evidence Docs</span><strong>{selectedClaimDocuments.length || "None selected"}</strong></div>
              </div>

              <div className="section"><h3>Rationale</h3><p>{result.rationale}</p></div>

              <div className="section">
                <h3>Operational Findings</h3>
                <ul>
                  <li><strong>Covered Items:</strong> {(result.covered_items || []).join(", ") || "Not found"}</li>
                  <li><strong>Exclusions:</strong> {(result.exclusions || []).join(", ") || "Not found"}</li>
                  <li><strong>Missing Information:</strong> {(result.missing_information || []).join(", ") || "None"}</li>
                  <li><strong>Next Steps:</strong> {(result.next_steps || []).join(", ") || "Review completed"}</li>
                </ul>
              </div>

              {result.document_checklist && (
                <div className="section">
                  <h3>Claim Document Checklist</h3>
                  <ul>
                    {(result.document_checklist.required || []).map((item) => (
                      <li key={item.document_type}>
                        <strong>{item.present ? "Present" : "Missing"}:</strong> {item.label}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {result.rag_evaluation && (
                <div className="section">
                  <h3>RAG Evaluation</h3>
                  <ul>
                    <li><strong>Grounded:</strong> {result.rag_evaluation.grounded ? "Yes" : "Needs review"}</li>
                    <li><strong>Sources:</strong> {result.rag_evaluation.source_count || 0}</li>
                    <li><strong>Policy Sources:</strong> {result.rag_evaluation.policy_source_count || 0}</li>
                    <li><strong>Claim Evidence Sources:</strong> {result.rag_evaluation.claim_source_count || 0}</li>
                    <li><strong>Warnings:</strong> {(result.rag_evaluation.warnings || []).join(", ") || "None"}</li>
                  </ul>
                </div>
              )}

              {result.escalation_required && (
                <div className="section warning-panel">
                  <h3>Human Review Required</h3>
                  <p>This decision was escalated because the evidence was low-confidence or incomplete.</p>
                </div>
              )}

              <div className="section">
                <h3>Explainability Trail</h3>
                <p>{Array.isArray(result.explanation_trail)
                  ? result.explanation_trail.join(" | ")
                  : (result.explanation_trail || result.next_steps?.join(" | ") || "No additional trail recorded.")}</p>
              </div>

              <div className="section"><h3>Evidence Summary</h3><p>{result.evidence_summary || "No structured evidence was returned."}</p></div>

              {Array.isArray(result.sources) && result.sources.length > 0 && (
                <div className="section source-panel">
                  <h3>Retrieved Sources</h3>
                  <ul>
                    {result.sources.map((source, index) => (
                      <li key={index}>
                        <strong>{source.source || "unknown source"}</strong>
                        {source.page && <span> - page: {source.page}</span>}
                        <div className="source-excerpt">{source.excerpt || "No excerpt available."}</div>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}

          <div className="result-card history-card">
            <h2>Claim History</h2>
            <table className="enterprise-table">
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Question</th>
                  <th>Decision</th>
                  <th>Confidence</th>
                  <th>Created By</th>
                  <th>Details</th>
                </tr>
              </thead>
              <tbody>
                {claims.length === 0 && (
                  <tr><td colSpan="6">No claim analyses yet.</td></tr>
                )}
                {claims.map((claim) => (
                  <tr key={claim.id}>
                    <td>{formatDate(claim.created_at)}</td>
                    <td>{claim.question}</td>
                    <td><span className={decisionClass(claim.decision)}>{claim.decision}</span></td>
                    <td>{claim.confidence}</td>
                    <td>{claim.created_by}</td>
                    <td><Link to={`/claims/${claim.id}`}>Open</Link></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}

export default ClaimAnalysis;
