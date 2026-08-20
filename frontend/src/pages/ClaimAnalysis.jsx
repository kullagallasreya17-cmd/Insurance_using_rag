import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import api from "../api";
import { getUser } from "../auth";
import Navbar from "../components/Navbar";
import Sidebar from "../components/Sidebar";
import "./ClaimAnalysis.css";

function ClaimAnalysis() {
  const user = getUser() || {};
  const navigate = useNavigate();
  const canAnalyzeClaims = ["admin", "customer"].includes((user.role || "customer").toLowerCase());
  const [mode, setMode] = useState("claim");
  const [question, setQuestion] = useState("");
  const [diagnosis, setDiagnosis] = useState("");
  const [hospitalName, setHospitalName] = useState("");
  const [hospitalLocation, setHospitalLocation] = useState("");
  const [claimAmount, setClaimAmount] = useState("");
  const [admissionDate, setAdmissionDate] = useState("");
  const [dischargeDate, setDischargeDate] = useState("");
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
        analysis_mode: mode,
        question,
        treatment_details: mode === "claim" ? question : null,
        diagnosis: diagnosis || null,
        hospital_name: hospitalName || null,
        hospital_location: hospitalLocation || null,
        admission_date: admissionDate || null,
        discharge_date: dischargeDate || null,
        claim_amount: claimAmount ? Number(claimAmount) : null,
        policy_category: mode === "claim" ? policyCategory : null,
        policy_document_id: mode === "claim" && selectedPolicyId ? Number(selectedPolicyId) : null,
        claim_document_ids: mode === "claim" ? selectedClaimDocumentIds.map((id) => Number(id)) : [],
        enable_web_search: mode !== "policy",
      });
      setResult(response.data);
      if (response.data.analysis_type === "claim_analysis") await fetchClaims();
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
          <div className="workspace-header">
            <div><span className="section-kicker">Insurance AI Platform / Investigation</span><h1>Claim Investigation &amp; Analysis</h1><p>Keep policy truth, uploaded evidence, current web information, and AI assessment visibly separate.</p></div>
            <button className="secondary-button" onClick={() => navigate("/documents")}>+ Upload document</button>
          </div>

          <div className="mode-switcher" aria-label="Question type">
            <button className={mode === "claim" ? "mode-card active" : "mode-card"} onClick={() => { setMode("claim"); setResult(null); }}><strong>Actual Claim Analysis</strong><span>Policy + uploaded evidence + claim details</span></button>
            <button className={mode === "policy" ? "mode-card active" : "mode-card"} onClick={() => { setMode("policy"); setResult(null); }}><strong>Policy Question</strong><span>Policy clauses and citations only</span></button>
            <button className={mode === "web" ? "mode-card active" : "mode-card"} onClick={() => { setMode("web"); setResult(null); }}><strong>General / Web Question</strong><span>Current hospitals, treatments, and costs</span></button>
          </div>

          {canAnalyzeClaims ? (
            <>
              <div className={`analysis-box ${mode}-mode`}>
                <div className="field-group">
                    <label className="field-label">{mode === "claim" ? "Claim question" : mode === "policy" ? "Policy question" : "Real-world question"}</label>
                  <input
                    type="text"
                      placeholder={mode === "claim" ? "Is my knee replacement claim covered and what amount may be payable?" : mode === "policy" ? "Does my policy cover knee replacement?" : "How much does knee replacement cost in Bangalore?"}
                    value={question}
                    onChange={(event) => setQuestion(event.target.value)}
                  />
                </div>

                <div className="question-chips">
                  {(mode === "claim" ? ["Is this treatment covered?", "Analyze my hospital bill", "Estimate eligible claim amount", "Check missing documents"] : mode === "policy" ? ["Does my policy cover knee replacement?", "What are my exclusions?", "What is my waiting period?"] : ["How much does knee replacement cost in Bangalore?", "Compare treatment costs between hospitals", "Which hospitals provide this treatment?"]).map((item) => <button key={item} onClick={() => setQuestion(item)}>{item}</button>)}
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
                  <label className="field-label">Admission date (optional)</label>
                  <input type="date" value={admissionDate} onChange={(event) => setAdmissionDate(event.target.value)} />
                </div>

                <div className="field-group">
                  <label className="field-label">Discharge date (optional)</label>
                  <input type="date" value={dischargeDate} onChange={(event) => setDischargeDate(event.target.value)} />
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
                  <label className="field-label">Hospital location / city</label>
                  <input
                    type="text"
                    placeholder="Example: Apollo Hospital, Chennai"
                    value={hospitalLocation}
                    onChange={(event) => setHospitalLocation(event.target.value)}
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
                {loading ? "Analysis in progress..." : mode === "claim" ? "Analyze Claim" : mode === "policy" ? "Ask Policy RAG" : "Search Current Information"}
              </button>
            </>
          ) : (
            <div className="result-card">
              <h2>Claim Audit View</h2>
              <p>Auditors can inspect claim history, retrieved sources, RAG evaluation, and explanation trails.</p>
            </div>
          )}

          {result && result.analysis_type !== "claim_analysis" && (
            <div className="result-card routed-result-card">
              <div className="result-header-row"><div><span className="section-kicker">Routed response</span><h2>{result.analysis_type === "policy_question" ? "Policy answer" : result.analysis_type === "document_question" ? "Document evidence answer" : "Real-world information"}</h2></div><span className="route-badge">{result.analysis_type === "policy_question" ? "Policy RAG" : result.analysis_type === "document_question" ? "Document RAG" : "Web search"}</span></div>
              <p className="routed-answer">{result.answer}</p>
              {(result.analysis_type === "policy_question" || result.analysis_type === "document_question") && <div className="section source-panel"><h3>{result.analysis_type === "policy_question" ? "Policy evidence" : "Uploaded document evidence"}</h3><ul>{(result.sources || []).map((source, index) => <li key={index}><strong>{source.filename || source.source || "Retrieved source"}</strong>{source.page && ` - page: ${source.page}`}<div className="source-excerpt">{source.excerpt || "Retrieved evidence."}</div></li>)}</ul></div>}
              {result.analysis_type === "web_question" && <div className="section web-research-panel"><h3>Real-world information</h3>{result.web_search_error && <p>Web information could not be retrieved.</p>}<ul>{(result.web_sources || []).map((source) => <li key={source.url}><strong>{source.title || "External source"}</strong><p>{source.snippet || source.content || "No extracted information available."}</p><small>{source.source || "External source"} · {source.search_timestamp || "Timestamp unavailable"}</small><br /><a href={source.url} target="_blank" rel="noreferrer">View source</a></li>)}</ul>{!result.web_sources?.length && !result.web_search_error && <p>No web results were returned.</p>}<small>Web estimates are informational and do not represent insurance-approved reimbursement.</small></div>}
            </div>
          )}

          {result && result.analysis_type === "claim_analysis" && (
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

              {result.financials && <div className="section financial-panel"><h3>Financial Assessment</h3><ul><li><strong>Claimed amount:</strong> {result.financials.claim_amount ? `Rs. ${Number(result.financials.claim_amount).toLocaleString()}` : "Unable to determine from available evidence."}</li><li><strong>Eligible amount:</strong> {result.financials.eligible_amount ? `Rs. ${Number(result.financials.eligible_amount).toLocaleString()}` : "Unable to determine from available evidence."}</li><li><strong>Deductible:</strong> {result.financials.deductible ? `Rs. ${Number(result.financials.deductible).toLocaleString()}` : "Unable to determine from available evidence."}</li><li><strong>Co-pay:</strong> {result.financials.co_payment ? `Rs. ${Number(result.financials.co_payment).toLocaleString()}` : "Unable to determine from available evidence."}</li></ul></div>}

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

              {result.hospital_research && (result.hospital_research.summary || result.hospital_research.sources?.length > 0) && (
                <div className="section web-research-panel">
                  <h3>Hospital Cost Research</h3>
                  <p><strong>Hospital:</strong> {result.hospital_research.hospital_name || "Not provided"}</p>
                  <p><strong>Location:</strong> {result.hospital_research.location || "Not provided"}</p>
                  <p>{result.hospital_research.summary || "No public estimate found."}</p>
                  {result.hospital_research.amount_assessment && (
                    <p>
                      <strong>Amount check:</strong>{" "}
                      {result.hospital_research.amount_assessment.message}
                    </p>
                  )}
                  <small>{result.hospital_research.disclaimer}</small>
                  {result.hospital_research.sources?.length > 0 && (
                    <ul>
                      {result.hospital_research.sources.map((source) => (
                        <li key={source.url}><a href={source.url} target="_blank" rel="noreferrer">{source.title}</a></li>
                      ))}
                    </ul>
                  )}
                </div>
              )}

              {!result.hospital_research && <div className="section web-not-used"><h3>Real-world information</h3><p>Web search was not required for this claim analysis. Coverage decisions remain grounded in policy and uploaded evidence.</p></div>}

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
