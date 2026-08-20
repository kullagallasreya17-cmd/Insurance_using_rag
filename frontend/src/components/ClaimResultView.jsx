import { useState } from "react";

const currency = (value) => {
  if (value === null || value === undefined || value === "") return "Cannot be determined yet";
  return `Rs. ${Number(value).toLocaleString("en-IN")}`;
};

const cleanDocumentName = (source) => {
  const value = source?.filename || source?.document_name || source?.source || "Supporting document";
  return value.split(/[\\/]/).pop();
};

const humanize = (value) => String(value || "")
  .replace(/Hospital network status UNKNOWN; verify provider\.?/gi, "Hospital network status needs to be verified.")
  .replace(/Policy document evidence/gi, "Policy document")
  .replace(/Claim evidence/gi, "Supporting claim documents")
  .replace(/LLM service configuration/gi, "AI service configuration")
  .replace(/LLM service response/gi, "AI service response")
  .replace(/Unable to determine from available evidence/gi, "We need more information to confirm this.");

const statusCopy = {
  approved: { label: "Covered", className: "friendly-covered", icon: "OK" },
  rejected: { label: "Not Covered", className: "friendly-not-covered", icon: "!" },
  needs_review: { label: "Needs Review", className: "friendly-review", icon: "?" },
};

function FriendlyStatus({ decision }) {
  const status = statusCopy[(decision || "needs_review").toLowerCase()] || statusCopy.needs_review;
  return <span className={`friendly-status ${status.className}`}><span>{status.icon}</span>{status.label}</span>;
}

function DetailCard({ label, value }) {
  return <div className="friendly-detail"><span>{label}</span><strong>{value || "Not provided"}</strong></div>;
}

function Section({ title, children, className = "" }) {
  return <section className={`friendly-section ${className}`}><h3>{title}</h3>{children}</section>;
}

function EvidenceList({ sources = [] }) {
  const [open, setOpen] = useState(null);
  if (!sources.length) return <p className="friendly-muted">No supporting documents were found.</p>;
  return <div className="friendly-evidence-list">{sources.slice(0, 8).map((source, index) => {
    const isOpen = open === index;
    return <article className="friendly-evidence" key={`${source.document_id || source.url || source.source}-${index}`}>
      <button className="friendly-evidence-toggle" onClick={() => setOpen(isOpen ? null : index)}>
        <span className="document-icon">DOC</span><span><strong>{cleanDocumentName(source)}</strong><small>{source.evidence_role === "claim" ? "Medical or claim information used" : "Policy information used"}{source.page && ` · Page ${source.page}`}</small></span><span>{isOpen ? "Hide" : "View"}</span>
      </button>
      {isOpen && <div className="friendly-evidence-detail"><p><strong>Page:</strong> {source.page || "Not available"}</p><p><strong>Relevant information:</strong> {source.excerpt || "Relevant information was used from this document."}</p></div>}
    </article>;
  })}</div>;
}

function DocumentsChecklist({ result }) {
  const required = result.document_checklist?.required || [];
  const received = required.filter((item) => item.present);
  const missing = required.filter((item) => !item.present);
  const fallbackMissing = (result.missing_information || []).filter((item) => /document|bill|prescription|report|receipt/i.test(item));
  return <Section title="Documents needed"><div className="document-status-columns"><div><h4>Documents received</h4>{received.length ? received.map((item) => <p className="friendly-check" key={item.document_type}>OK {item.label}</p>) : <p className="friendly-muted">No supporting documents confirmed.</p>}</div><div><h4>Documents still needed</h4>{missing.length || fallbackMissing.length ? (missing.length ? missing : fallbackMissing.map((label) => ({ label }))).map((item, index) => <p className="friendly-missing" key={`${item.label}-${index}`}>○ {item.label}</p>) : <p className="friendly-check">OK No additional documents reported.</p>}</div></div></Section>;
}

function ClaimResult({ result, diagnosis, hospitalName, claimAmount, policyLabel }) {
  const decision = (result.decision || "needs_review").toLowerCase();
  const financials = result.financials || {};
  const missing = result.missing_information || [];
  const covered = result.covered_items || [];
  const exclusions = result.exclusions || [];
  const summary = result.rationale || (decision === "approved" ? "Your claim appears to meet the available policy requirements." : "We need more information to complete this claim assessment.");
  const nextSteps = (result.next_steps || []).filter((step) => !/escalate|human underwriter|manual review/i.test(step)).slice(0, 3);
  const conditions = [
    { label: "Waiting period", state: result.waiting_period_eligible === false ? "warning" : "needs", text: result.waiting_period_eligible === false ? "Waiting period may not be satisfied" : "Needs verification" },
    { label: "Coverage limit", state: financials.coverage_limit ? "ok" : "needs", text: financials.coverage_limit ? currency(financials.coverage_limit) : "Needs verification" },
    { label: "Relevant exclusion", state: exclusions.length ? "warning" : "ok", text: exclusions.length ? exclusions.join(", ") : "No relevant exclusion identified" },
  ];
  return <div className="friendly-result">
    <div className="friendly-result-header"><div><span className="section-kicker">Claim result</span><h2>Claim assessment</h2></div><FriendlyStatus decision={decision} /></div>
    <p className="friendly-summary">{summary}</p>
    <Section title="Key details"><div className="friendly-details-grid"><DetailCard label="Treatment" value={diagnosis || result.treatment_details || "Treatment described in claim question"} /><DetailCard label="Diagnosis" value={diagnosis} /><DetailCard label="Hospital" value={hospitalName || result.hospital_research?.hospital_name} /><DetailCard label="Claim amount" value={claimAmount ? currency(claimAmount) : "Not provided"} /><DetailCard label="Policy" value={policyLabel} /></div></Section>
    <Section title="Why this result?"><ul className="friendly-list">{covered.slice(0, 3).map((item) => <li className="friendly-check" key={item}>OK {item}</li>)}<li className={missing.length ? "friendly-warning" : "friendly-check"}>{missing.length ? "! Some information is still missing." : "OK The available information supports this assessment."}</li></ul><p className="friendly-note">{summary}</p></Section>
    <Section title="What is covered?"><ul className="friendly-list">{covered.length ? covered.slice(0, 5).map((item) => <li className="friendly-check" key={item}>OK {item}</li>) : <li className="friendly-unknown">? Coverage could not be confirmed from the available policy.</li>}</ul></Section>
    <Section title="What is not confirmed?"><ul className="friendly-list">{missing.length ? missing.slice(0, 5).map((item) => <li className="friendly-warning" key={item}>! {item.replace(/UNKNOWN/gi, "needs verification")}</li>) : <li className="friendly-check">OK No additional information was reported as missing.</li>}</ul></Section>
    <DocumentsChecklist result={{ ...result, missing_information: missing.map(humanize) }} />
    <Section title="Policy conditions"><div className="condition-list">{conditions.map((condition) => <div className="condition-row" key={condition.label}><strong>{condition.label}</strong><span className={`condition-${condition.state}`}>{condition.state === "ok" ? "OK" : "!"} {condition.text}</span></div>)}</div></Section>
    <Section title="Claim amount"><div className="payment-grid"><DetailCard label="Claim amount" value={financials.claim_amount ? currency(financials.claim_amount) : claimAmount ? currency(claimAmount) : "Not provided"} /><DetailCard label="Estimated payable amount" value={financials.eligible_amount && financials.eligible_amount !== financials.claim_amount ? currency(financials.eligible_amount) : "Cannot be determined yet"} /></div><p className="friendly-note">Final payable amount will be calculated after reviewing applicable policy limits, deductible, co-pay, and eligible expenses.</p></Section>
    <Section title="What should you do next?"><ol className="friendly-next-steps">{(nextSteps.length ? nextSteps.map(humanize) : ["Upload any missing claim documents", "Verify the hospital network status", "Confirm applicable policy limits with the insurer"]).map((step, index) => <li key={`${step}-${index}`}>{step}</li>)}</ol></Section>
    <Section title="Supporting documents"><EvidenceList sources={result.sources || []} /></Section>
    {(result.escalation_required || decision === "needs_review") && <div className="human-review"><strong>! Human review recommended</strong><p>Your claim cannot be finalized automatically because some information is missing or needs verification.</p></div>}
    <p className="friendly-disclaimer">This is an AI-assisted assessment based on the available policy and claim documents. Final claim approval should be confirmed by the insurer or claims team.</p>
  </div>;
}

function PolicyResult({ result }) {
  return <div className="friendly-result"><div className="friendly-result-header"><div><span className="section-kicker">Policy answer</span><h2>Policy coverage</h2></div><span className="route-badge">Policy RAG</span></div><p className="friendly-summary">{result.answer}</p><Section title="Important conditions"><ul className="friendly-list"><li className="friendly-check">OK Relevant policy clauses were reviewed.</li><li className="friendly-warning">! Waiting period and applicable limits should be checked.</li></ul></Section><Section title="Policy source"><EvidenceList sources={result.sources || []} /></Section></div>;
}

function WebResult({ result }) {
  if (result.web_search_error || !result.web_sources?.length) return <div className="friendly-result"><div className="friendly-result-header"><div><span className="section-kicker">Current information</span><h2>Web search unavailable</h2></div><span className="friendly-status friendly-not-covered"><span>!</span>Unavailable</span></div><p className="friendly-summary">We couldn't retrieve current information from the web right now. No current web information was used in this answer.</p></div>;
  return <div className="friendly-result"><div className="friendly-result-header"><div><span className="section-kicker">Current information</span><h2>Real-world information</h2></div><span className="route-badge">Web search</span></div><p className="friendly-summary">Current public information was retrieved from the internet. Treatment costs and hospital information may change.</p><Section title="Sources"><div className="friendly-web-list">{result.web_sources.map((source) => <article className="friendly-web-source" key={source.url}><strong>{source.title || "External source"}</strong><small>{source.source || "External source"}</small><p>{source.snippet || source.content || "No extracted information available."}</p><a href={source.url} target="_blank" rel="noreferrer">View source</a></article>)}</div><p className="friendly-disclaimer">Web information is current public information and is not an insurance-approved reimbursement amount.</p></Section></div>;
}

export default function ClaimResultView({ result, diagnosis, hospitalName, claimAmount, policyLabel }) {
  if (result.response_type === "claim_analysis") return <ClaimResult result={result} diagnosis={diagnosis} hospitalName={hospitalName} claimAmount={claimAmount} policyLabel={policyLabel} />;
  if (result.response_type === "policy_answer" || result.response_type === "document_answer") return <PolicyResult result={result} />;
  return <WebResult result={result} />;
}
