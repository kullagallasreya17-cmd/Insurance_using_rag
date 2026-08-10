import "./UploadReports.css";
import Navbar from "../components/Navbar";
import Sidebar from "../components/Sidebar";
import FileUploader from "../components/FileUploader";

function UploadReports() {
  return (
    <div className="reports-container">

      <Sidebar />

      <div className="reports-main">

        <Navbar />

        <div className="reports-content">

          <h1>📁 Upload Reports</h1>

          <p>
            Upload any report documents (medical, bills, policies, or other PDFs). These documents will be processed using OCR,
            indexed into the vector database, and used for AI-based analysis and question answering.
          </p>

          <div className="report-cards">

            <div className="report-card">
              <span>🏥</span>
              <h3>Medical Report</h3>
              <p>Doctor diagnosis and treatment summary.</p>
            </div>

            <div className="report-card">
              <span>🧾</span>
              <h3>Hospital Bill</h3>
              <p>Hospital invoice and payment details.</p>
            </div>

            <div className="report-card">
              <span>💊</span>
              <h3>Prescription</h3>
              <p>Medicines prescribed by the doctor.</p>
            </div>

            <div className="report-card">
              <span>🩺</span>
              <h3>Lab Report</h3>
              <p>Blood test, scan and diagnostic reports.</p>
            </div>

          </div>

          <div className="upload-section">

            <FileUploader
              title="Upload Report or Document"
              endpoint="upload-report"
              defaultCategory="medical_document"
            />

            <FileUploader
              title="Upload Additional Document"
              endpoint="upload-bill"
              defaultCategory="other"
            />

            <FileUploader
              title="Upload Additional Document"
              endpoint="upload-prescription"
              defaultCategory="other"
            />

            <FileUploader
              title="Upload Additional Document"
              endpoint="upload-lab-report"
              defaultCategory="other"
            />

          </div>

          <div className="workflow">

            <h2>Medical Report Processing Flow</h2>

            <div className="flow">

              <div className="flow-card">
                📄
                <h4>Upload Reports</h4>
              </div>

              <div className="flow-card">
                🔍
                <h4>OCR Extraction</h4>
              </div>

              <div className="flow-card">
                ✂️
                <h4>Chunking</h4>
              </div>

              <div className="flow-card">
                🧠
                <h4>Embeddings</h4>
              </div>

              <div className="flow-card">
                🗄️
                <h4>Vector Database</h4>
              </div>

              <div className="flow-card">
                🤖
                <h4>Ready for AI Analysis</h4>
              </div>

            </div>

          </div>

        </div>

      </div>

    </div>
  );
}

export default UploadReports;
