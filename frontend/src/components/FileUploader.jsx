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
  const [message, setMessage] = useState("");
  const [messageType, setMessageType] = useState("info");
  const [progressStep, setProgressStep] = useState(0);
  const [uploadResult, setUploadResult] = useState(null);
  const [history, setHistory] = useState([]);
  const [dragActive, setDragActive] = useState(false);
  const historyDocumentType = ENDPOINT_DOCUMENT_TYPES[endpoint] || "medical_report";

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
    if (!uploading) return undefined;

    const timer = window.setInterval(() => {
      setProgressStep((current) => (current + 1) % PROGRESS_STEPS.length);
    }, 700);

    return () => window.clearInterval(timer);
  }, [uploading]);

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
      setProgressStep(0);
      setMessage("");
      setMessageType("info");
      setUploadResult(null);

      if (allowedCategories.length && !allowedCategories.includes(category)) {
        setMessageType("error");
        setMessage("The selected category is not allowed for your role. Please choose a different category.");
        return;
      }
      setUploadResult(null);
      setMessage("Uploading documents. Indexing will run in the background...");
      setMessageType("info");

      let documentId = null;
      // send files sequentially to the same endpoint (backend expects a single file per request)
      for (const file of selectedFiles) {
        const formData = new FormData();
        formData.append("file", file);
        try {
          const response = await api.post(`/${endpoint}?category=${category}&replace_existing=false`, formData);
          // keep last returned document id for history polling
          documentId = response.data?.document_id || documentId;
          // merge response into uploadResult to show last file metadata
          setUploadResult((current) => ({ ...(current || {}), ...response.data }));
        } catch (err) {
          console.error("Upload failed for a file", err);
        }
      }

      let indexedDocument = null;
      for (let attempt = 0; attempt < 30 && documentId; attempt += 1) {
        await new Promise((resolve) => window.setTimeout(resolve, 1500));
        const documents = await loadHistory();
        indexedDocument = documents.find((item) => item.id === documentId);

        if (indexedDocument) {
          setUploadResult((current) => ({ ...current, ...indexedDocument }));
          const status = (indexedDocument.status || "").toLowerCase();

          if (status === "indexed") {
            setMessage("Document uploaded and indexed successfully.");
            setMessageType("success");
            break;
          }

          if (status === "failed") {
            setMessage("Document uploaded, but indexing failed. Check backend logs for the exact error.");
            setMessageType("error");
            break;
          }
        }
      }

      if (documentId && (!indexedDocument || (indexedDocument.status || "").toLowerCase() === "processing")) {
        setMessage("Document uploaded and still indexing. Refresh the history in a moment.");
        setMessageType("info");
      }

      if (!documentId) {
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
      setProgressStep(PROGRESS_STEPS.length - 1);
      // clear selected files after upload
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

      {uploading && (
        <div className="progress-panel">
          <p>{PROGRESS_STEPS[progressStep]}</p>
          <div className="progress-bar">
            <div className="progress-fill" style={{ width: `${((progressStep + 1) / PROGRESS_STEPS.length) * 100}%` }} />
          </div>
        </div>
      )}

      {message && <p className={`message ${messageType}`}>{message}</p>}

      {uploadResult && (
        <div className="result-card">
          <h3>Upload Complete</h3>
          <p><strong>File:</strong> {uploadResult.filename}</p>
          <p><strong>Pages:</strong> {uploadResult.pages || 0}</p>
          <p><strong>Chunks:</strong> {uploadResult.chunks || 0}</p>
          <p><strong>Words:</strong> {uploadResult.word_count ?? uploadResult.words ?? 0}</p>
          <p><strong>Processing Time:</strong> {uploadResult.processing_time_seconds || 0}s</p>
          <p><strong>Status:</strong> {uploadResult.status || "processing"}</p>
          {uploadResult.preview_text && (
            <div className="preview-box">
              <strong>Preview:</strong>
              <p>{uploadResult.preview_text}</p>
            </div>
          )}
        </div>
      )}

      <div className="history-panel">
        <h3>Recent Upload History</h3>
        {historyRows.length === 0 ? <p>No uploads yet.</p> : (
          <ul>
            {historyRows.map((item) => (
              <li key={item.id}>
                <span>{item.filename}</span>
                <span>{item.category}</span>
                <span>{item.status}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

export default FileUploader;
