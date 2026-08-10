import { Link } from "react-router-dom";
import "./Landing.css";

function Landing() {
  return (
    <main className="landing-page">
      <section className="landing-hero">
        <div className="landing-copy">
          <span>Enterprise Insurance AI</span>
          <h1>Grounded policy intelligence for claims, documents, and service teams.</h1>
          <p>
            Upload policy documents, index them into a RAG knowledge base, ask
            grounded questions, and generate claim decisions with audit-ready evidence.
          </p>
          <div className="landing-actions">
            <Link to="/login">Sign In</Link>
            <Link to="/register" className="landing-secondary">Create Account</Link>
          </div>
        </div>
      </section>
    </main>
  );
}

export default Landing;
