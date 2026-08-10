import { useState } from "react";
import "./UploadPolicy.css";
import Navbar from "../components/Navbar";
import Sidebar from "../components/Sidebar";
import FileUploader from "../components/FileUploader";

function UploadPolicy() {
  const [selectedCategory, setSelectedCategory] = useState("other");

  const categories = [
    { key: "health_policy", label: "Health" },
    { key: "vehicle_policy", label: "Vehicle" },
    { key: "life_policy", label: "Life" },
    { key: "other", label: "Others" },
  ];

  return (
    <div className="upload-policy-container">

      <Sidebar />

      <div className="upload-policy-main">

        <Navbar />

        <div className="upload-policy-content">

          <h1>📄 Upload Policy or Report</h1>

          <p>
            Upload policy or report documents (PDF) to build the knowledge base for the RAG system.
            You can upload multiple documents and select a category below (including "Others").
          </p>

          <div className="info-cards">

            <div className="info-card">
              <h3>Supported Format</h3>
              <p>PDF Documents</p>
            </div>

            <div className="info-card">
              <h3>Maximum Size</h3>
              <p>20 MB</p>
            </div>

            <div className="info-card">
              <h3>Processing</h3>
              <p>OCR + Embedding + Vector DB</p>
            </div>

          </div>

          <div style={{ margin: "12px 0", display: "flex", gap: 8 }}>
            {categories.map((c) => (
              <button
                key={c.key}
                className={`table-action-button ${selectedCategory === c.key ? "" : "secondary"}`}
                onClick={() => setSelectedCategory(c.key)}
              >
                {c.label}
              </button>
            ))}
          </div>

          <FileUploader
            title="Upload Policy or Report"
            endpoint="upload-policy"
            defaultCategory={selectedCategory}
          />

        </div>

      </div>

    </div>
  );
}

export default UploadPolicy;
