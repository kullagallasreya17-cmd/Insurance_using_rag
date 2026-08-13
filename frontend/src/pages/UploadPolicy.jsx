import { useEffect, useState } from "react";
import api from "../api";
import "./UploadPolicy.css";
import Navbar from "../components/Navbar";
import Sidebar from "../components/Sidebar";
import FileUploader from "../components/FileUploader";

const CATEGORY_LABELS = {
  health_policy: "Health",
  vehicle_policy: "Vehicle",
  life_policy: "Life",
  claim_procedure: "Claim Procedure",
  terms_conditions: "Terms & Conditions",
  faq: "FAQ",
  medical_document: "Medical Document",
  other: "Others",
};

function UploadPolicy() {
  const [selectedCategory, setSelectedCategory] = useState("other");
  const [categories, setCategories] = useState([
    "health_policy",
    "vehicle_policy",
    "life_policy",
    "other",
  ]);
  const [loadingCategories, setLoadingCategories] = useState(true);
  const [categoryError, setCategoryError] = useState("");

  useEffect(() => {
    const loadCategories = async () => {
      try {
        const response = await api.get("/knowledge-categories");
        const allowed = response.data?.categories || [];
        if (allowed.length) {
          setCategories(allowed);
          if (!allowed.includes(selectedCategory)) {
            setSelectedCategory(allowed[0]);
          }
          setCategoryError("");
        } else {
          setCategoryError("No upload categories are currently available for your role.");
        }
      } catch (error) {
        console.error("Unable to load categories", error);
        setCategoryError("Unable to load categories. Please refresh the page.");
      } finally {
        setLoadingCategories(false);
      }
    };

    loadCategories();
  }, []);

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

          <div style={{ margin: "12px 0", display: "flex", flexWrap: "wrap", gap: 8 }}>
            {loadingCategories ? (
              <p>Loading categories...</p>
            ) : categories.length > 0 ? (
              categories.map((categoryKey) => (
                <button
                  key={categoryKey}
                  className={`table-action-button ${selectedCategory === categoryKey ? "" : "secondary"}`}
                  onClick={() => setSelectedCategory(categoryKey)}
                >
                  {CATEGORY_LABELS[categoryKey] || categoryKey.replace(/_/g, " ")}
                </button>
              ))
            ) : (
              <p className="category-error">{categoryError}</p>
            )}
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
