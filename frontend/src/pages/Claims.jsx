import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api from "../api";
import PortalLayout from "../components/PortalLayout";

function Claims() {
  const [claims, setClaims] = useState([]);

  useEffect(() => {
    api.get("/claims").then((response) => setClaims(response.data.claims || []));
  }, []);

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
    <PortalLayout
      title="Claims"
      subtitle="Analyses and Q&A generated from retrieved policy and report context."
    >
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
            <tr>
              <td colSpan="6">No claim analyses yet.</td>
            </tr>
          )}
          {claims.map((claim) => (
            <tr key={claim.id}>
              <td>{formatDate(claim.created_at)}</td>
              <td>{claim.question}</td>
              <td><span className={statusClass(claim.decision)}>{claim.decision}</span></td>
              <td>{claim.confidence}</td>
              <td>{claim.created_by}</td>
              <td><Link to={`/claims/${claim.id}`}>Open</Link></td>
            </tr>
          ))}
        </tbody>
      </table>
    </PortalLayout>
  );
}

export default Claims;
