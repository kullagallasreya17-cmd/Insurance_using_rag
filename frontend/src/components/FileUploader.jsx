import { useCallback, useEffect, useMemo, useState } from "react";
import api from "../api";
import "./FileUploader.css";

const PROGRESS_STEPS = [
  "Uploading document...",
  "Extracting text...",
  "Creating chunks...",
  "Generating embeddings...",
  "Saving to vector store...",
  "Completed",
];

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

const STATIC_CATEGORIES = [
  "health_policy",
  "vehicle_policy",
  "life_policy",
  "home_policy",
  "travel_policy",
  "personal_accident_policy",
  "critical_illness_policy",
  "property_policy",
  "claim_procedure",
  "terms_conditions",
  "faq",
  "medical_document",
  "other",
];
const ENDPOINT_DOCUMENT_TYPES = {
  "upload-policy": "policy",
  "upload-report": "medical_report",
  "upload-bill": "hospital_bill",
  "upload-prescription": "prescription",
  "upload-lab-report": "lab_report",
};

function formatCategoryLabel(category) {
  return CATEGORY_LABELS[category] || category.replace(/_/g, " ");
}

function getErrorMessage(error) {
  const data = error?.response?.data;

  if (typeof data === "string") {
    return data;
  }

  if (typeof data?.detail === "string") {
    return data.detail;
  }

  if (data?.detail && typeof data.detail === "object") {
    if (typeof data.detail.detail === "string") {
      return data.detail.detail;
    }
    if (typeof data.detail.message === "string") {
      return data.detail.message;
    }
    return JSON.stringify(data.detail);
  }

  if (typeof data?.message === "string") {
    return data.message;
  }

  if (typeof error?.message === "string") {
    return error.message;
  }

  return "Upload failed.";
}

function FileUploader({ title, endpoint, defaultCategory = "medical_document" }) {
  const [selectedFiles, setSelectedFiles] = useState([]);
  const [category, setCategory] = useState(defaultCategory);
  useEffect(() => {
    setCategory(defaultCategory);
  }, [defaultCategory]);
  const [allowedCategories, setAllowedCategories] = useState([]);
  const [categoryError, setCategoryError] = useState("");
  const [uploading, setUploading] = useState(false);
  const [indexing, setIndexing] = useState(false);
  const [message, setMessage] = useState("");
  const [messageType, setMessageType] = useState("info");
  const [progressStep, setProgressStep] = useState(0);
  const [uploadResults, setUploadResults] = useState([]);
  const [history, setHistory] = useState([]);
  const [dragActive, setDragActive] = useState(false);
  const historyDocumentType = ENDPOINT_DOCUMENT_TYPES[endpoint] || "medical_report";

  const allUploadsComplete = uploadResults.length > 0 && uploadResults.every((result) => {
    const status = String(result.status || "").toLowerCase();
    return status === "indexed" || status === "failed";
  });

  const uploadResultsTitle = uploadResults.length === 0
    ? ""
    : allUploadsComplete
    ? "Upload Complete"
    : "Upload in Progress";

  const showProgress = uploading || indexing;

  const loadHistory = useCallback(async () => {
    const response = await api.get(`/upload-history?document_type=${historyDocumentType}`);
    const documents = response.data.documents || [];
    setHistory(documents);
    return documents;
  }, [historyDocumentType]);

  useEffect(() => {
    const loadInitialHistory = async () => {
      try {
        await loadHistory();
      } catch (error) {
        console.error("Unable to load upload history", error);
      }
    };

    loadInitialHistory();
  }, [loadHistory]);

  useEffect(() => {
    const loadAllowedCategories = async () => {
      try {
        const response = await api.get("/knowledge-categories");
        const categories = response.data?.categories || [];
        setAllowedCategories(categories.length ? categories : STATIC_CATEGORIES);

        if (!categories.length) {
          setCategoryError("You do not have access to any upload categories.");
        } else {
          setCategoryError("");
          if (!categories.includes(defaultCategory)) {
            setCategory(categories[0]);
          }
        }
      } catch (error) {
        console.error("Unable to load allowed categories", error);
        setAllowedCategories(STATIC_CATEGORIES);
        setCategory(defaultCategory);
      }
    };

    loadAllowedCategories();
  }, [defaultCategory]);

  useEffect(() => {
    const shouldAnimate = uploading || indexing;
    if (!shouldAnimate) return undefined;

    const timer = window.setInterval(() => {
      setProgressStep((current) => (current + 1) % PROGRESS_STEPS.length);
    }, 700);

    return () => window.clearInterval(timer);
  }, [uploading, indexing]);

  const handleFileChange = (event) => {
    const files = Array.from(event.target.files || []);
    if (!files.length) return;

    const allowedTypes = ["application/pdf", "image/png", "image/jpeg", "image/jpg"];
    const filtered = [];
    for (const file of files) {
      const ext = `.${file.name.split(".").pop()?.toLowerCase()}`;
      if (!allowedTypes.includes(file.type) && ![".pdf", ".png", ".jpg", ".jpeg"].includes(ext)) {
        continue;
      }
      if (file.size > 20 * 1024 * 1024) {
        continue;
      }
      filtered.push(file);
    }

    if (!filtered.length) {
      setMessageType("error");
      setMessage("No valid files selected. Only PDF, PNG and JPG under 20MB are allowed.");
      return;
    }

    setSelectedFiles(filtered);
    setMessage("");
    setMessageType("info");
  };

  const uploadFile = async () => {
    if (!selectedFiles || selectedFiles.length === 0) {
      setMessageType("error");
      setMessage("Please select one or more files.");
      return;
    }

    try {
      setUploading(true);
      setIndexing(true);
      setProgressStep(0);
      setMessage("");
      setMessageType("info");
      setUploadResults([]);

      if (allowedCategories.length && !allowedCategories.includes(category)) {
        setMessageType("error");
        setMessage("The selected category is not allowed for your role. Please choose a different category.");
        setUploading(false);
        setIndexing(false);
        return;
      }
      setMessage("Uploading documents. Indexing will run in the background...");
      setMessageType("info");

      let currentResults = [];

      for (const file of selectedFiles) {
        const formData = new FormData();
        formData.append("file", file);
        try {
          const response = await api.post(`/${endpoint}?category=${category}&replace_existing=false`, formData);
          const responseData = response.data || {};
          const result = {
            document_id: responseData.document_id,
            filename: responseData.filename || file.name,
            category,
            status: responseData.status || "processing",
            pages: responseData.pages ?? 0,
            chunks: responseData.chunks ?? 0,
            word_count: responseData.word_count ?? responseData.words ?? 0,
            processing_time_seconds: responseData.processing_time_seconds ?? 0,
          };
          currentResults.push(result);
          setUploadResults([...currentResults]);
        } catch (err) {
          console.error("Upload failed for a file", err);
          currentResults.push({
            document_id: null,
            filename: file.name,
            category,
            status: "failed",
            pages: 0,
            chunks: 0,
            word_count: 0,
            processing_time_seconds: 0,
          });
          setUploadResults([...currentResults]);
        }
      }

      const pendingDocumentIds = new Set(
        currentResults
          .filter((item) => item.document_id)
          .map((item) => item.document_id),
      );

      let attempts = 0;
      while (pendingDocumentIds.size > 0 && attempts < 30) {
        await new Promise((resolve) => window.setTimeout(resolve, 1500));
        const documents = await loadHistory();

        currentResults = currentResults.map((item) => {
          const matched = documents.find((doc) => doc.id === item.document_id);
          if (!matched) {
            return item;
          }

          const status = String(matched.status || item.status || "").toLowerCase();
          if (status === "indexed" || status === "failed") {
            pendingDocumentIds.delete(item.document_id);
          }

          return {
            ...item,
            ...matched,
            category: matched.category || item.category,
          };
        });

        setUploadResults([...currentResults]);
        attempts += 1;
      }

      const finishedResults = currentResults.filter((item) => {
        const status = String(item.status || "").toLowerCase();
        return status === "indexed" || status === "failed";
      });

      const allFinished = finishedResults.length === currentResults.length;
      const anyFailed = finishedResults.some((item) => String(item.status || "").toLowerCase() === "failed");

      if (allFinished) {
        if (anyFailed) {
          setMessage("One or more files failed to index. Check logs and retry if needed.");
          setMessageType("error");
        } else {
          setMessage("Document uploaded and indexed successfully.");
          setMessageType("success");
        }
      } else {
        setMessage("Document uploaded and still indexing. Refresh the history in a moment.");
        setMessageType("info");
      }

      setIndexing(false);
      if (!currentResults.some((item) => item.document_id)) {
        await loadHistory();
      }
    } catch (error) {
      if (error.response?.status === 409) {
        setMessageType("warning");
        setMessage("This policy has already been indexed. Choose replace or keep both on the backend.");
      } else {
        setMessageType("error");
        setMessage(getErrorMessage(error));
      }
    } finally {
      setUploading(false);
      setIndexing(false);
      if (allUploadsComplete) {
        setProgressStep(PROGRESS_STEPS.length - 1);
      } else {
        setProgressStep(0);
      }
      setSelectedFiles([]);
    }
  };

  const historyRows = useMemo(() => history.slice(0, 6), [history]);

  return (
    <div className="upload-card">
      <h2>{title}</h2>

      <select value={category} onChange={(event) => setCategory(event.target.value)}>
          {(allowedCategories.length ? allowedCategories : STATIC_CATEGORIES).map((option) => (
            <option key={option} value={option}>
              {formatCategoryLabel(option)}
            </option>
          ))}
      </select>

      {categoryError && <p className="message error">{categoryError}</p>}

      <label
        className={`drop-zone ${dragActive ? "drag-active" : ""}`}
        onDragOver={(event) => {
          event.preventDefault();
          setDragActive(true);
        }}
        onDragLeave={() => setDragActive(false)}
        onDrop={(event) => {
          event.preventDefault();
          setDragActive(false);
          const droppedFiles = Array.from(event.dataTransfer.files || []);
          if (droppedFiles.length) {
            const input = document.createElement("input");
            Object.defineProperty(input, "files", { value: droppedFiles });
            handleFileChange({ target: input });
          }
        }}
      >
        <span>{dragActive ? "Drop files here" : "Drag & Drop Files Here"}</span>
        <span>or</span>
        <span>Browse Files</span>
        <input type="file" accept=".pdf,.png,.jpg,.jpeg" multiple onChange={handleFileChange} />
      </label>

      {selectedFiles && selectedFiles.length > 0 && (
        <div className="file-details">
          <p><strong>Files:</strong></p>
          <ul>
            {selectedFiles.map((f, idx) => (
              <li key={idx}>{f.name} — {(f.size / 1024).toFixed(2)} KB</li>
            ))}
          </ul>
          <p><strong>Category:</strong> {category}</p>
        </div>
      )}

      <button onClick={uploadFile} disabled={uploading || Boolean(categoryError)}>
        {uploading ? "Processing..." : "Upload & Index"}
      </button>

      {showProgress && (
        <div className="progress-panel">
          <p>{PROGRESS_STEPS[progressStep]}</p>
          <div className="progress-bar">
            <div className="progress-fill" style={{ width: `${((progressStep + 1) / PROGRESS_STEPS.length) * 100}%` }} />
          </div>
        </div>
      )}

      {message && <p className={`message ${messageType}`}>{message}</p>}

      {uploadResults.length > 0 && (
        <div className="result-card">
          <h3>{uploadResultsTitle}</h3>
          <ul>
            {uploadResults.map((result) => {
              const status = String(result.status || "processing").toLowerCase();
              return (
                <li key={result.document_id || result.filename}>
                  <div className="result-header">
                    <span className="document-name">{result.filename}</span>
                    <span className={`file-status ${status}`}>{status.replace(/_/g, " ")}</span>
                  </div>
                  <div className="file-summary">
                    <span>Category: {formatCategoryLabel(result.category)}</span>
                    <span>Pages: {result.pages || 0}</span>
                    <span>Chunks: {result.chunks || 0}</span>
                    <span>Words: {result.word_count ?? result.words ?? 0}</span>
                    {result.processing_time_seconds > 0 && (
                      <span>Time: {result.processing_time_seconds.toFixed(2)}s</span>
                    )}
                  </div>
                  {status === "processing" && (
                    <p className="status-note">Indexing in progress. This may take a moment.</p>
                  )}
                  {status === "failed" && (
                    <p className="status-note error">Indexing failed. Please check the server logs or retry.</p>
                  )}
                </li>
              );
            })}
          </ul>
        </div>
      )}

      <div className="history-panel">
        <h3>Recent Upload History</h3>
        {historyRows.length === 0 ? <p>No uploads yet.</p> : (
          <ul>
            {historyRows.map((item) => (
              <li key={item.id}>
                <span>{item.filename}</span>
                <span>{formatCategoryLabel(item.category)}</span>
                <span>{String(item.status || "processing").replace(/_/g, " ")}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

export default FileUploader;
