import { useEffect, useState } from "react";
import api from "../api";
import "./UploadPolicy.css";
import Navbar from "../components/Navbar";
import Sidebar from "../components/Sidebar";
import FileUploader from "../components/FileUploader";

const CATEGORY_LABELS = {
  health_policy: "Health Policy",
  vehicle_policy: "Vehicle Policy",
  life_policy: "Life Policy",
  home_policy: "Home Policy",
  travel_policy: "Travel Policy",
  personal_accident_policy: "Personal Accident Policy",
  critical_illness_policy: "Critical Illness Policy",
  property_policy: "Property Policy",
  claim_procedure: "Claim Procedure",
  terms_conditions: "Terms & Conditions",
  faq: "FAQ",
  medical_document: "Medical Document",
  other: "Others",
};

function UploadPolicy() {
  const [selectedCategory, setSelectedCategory] = useState("health_policy");
  const [categories, setCategories] = useState([
    "health_policy",
    "vehicle_policy",
    "life_policy",
    "home_policy",
    "travel_policy",
    "personal_accident_policy",
    "critical_illness_policy",
    "property_policy",
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

          <h1>📄 Upload Policy Documents</h1>

          <p>
            Upload one or more policy documents (PDF) to build the knowledge base for the RAG system.
            This page supports multi-document uploads and lets you assign the correct category before indexing.
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

          {/* Category quick-buttons removed per request; selection is available in the dropdown below. */}

          <FileUploader
            title="Upload Policy Documents"
            endpoint="upload-policy"
            defaultCategory={selectedCategory}
          />

        </div>

      </div>

    </div>
  );
}

export default UploadPolicy;
