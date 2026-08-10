import "./Chatbot.css";
import Navbar from "../components/Navbar";
import Sidebar from "../components/Sidebar";
import ChatBox from "../components/ChatBox";

function Chatbot() {
  return (
    <div className="chatbot-page">

      <Sidebar />

      <div className="chatbot-main">

        <Navbar />

        <div className="chatbot-content">

          <div className="chatbot-header">

            <h1>🤖 Insurance AI Assistant</h1>

            <p>
              Ask questions about your insurance policy, medical reports,
              hospital bills, or claim eligibility. The AI assistant uses
              Retrieval-Augmented Generation (RAG) to retrieve relevant
              policy information and generate accurate responses.
            </p>

          </div>

          <div className="chatbot-info">

            <div className="info-card">

              <h3>📄 Policy Search</h3>

              <p>
                Searches uploaded insurance policy documents using
                vector embeddings.
              </p>

            </div>

            <div className="info-card">

              <h3>🏥 Medical Reports</h3>

              <p>
                Understands uploaded medical reports and hospital
                bills before answering.
              </p>

            </div>

            <div className="info-card">

              <h3>🤖 Gemini AI</h3>

              <p>
                Generates intelligent answers using retrieved
                policy context.
              </p>

            </div>

          </div>

          <ChatBox />

        </div>

      </div>

    </div>
  );
}

export default Chatbot;