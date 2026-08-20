import { useState } from "react";
import { Link } from "react-router-dom";
import api from "../api";
import "./Login.css";

function ForgotPassword() {
  const [email, setEmail] = useState("");
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);

  const submit = async (event) => {
    event.preventDefault();
    setLoading(true);
    try {
      const response = await api.post("/auth/forgot-password", { email });
      setMessage(response.data.message);
    } catch (error) {
      setMessage(error.response?.data?.detail || "If an account exists for this email, password reset instructions have been sent.");
    } finally {
      setLoading(false);
    }
  };

  return <main className="login-page"><form className="login-panel" onSubmit={submit}>
    <div className="brand-headline"><h1>Forgot Password</h1><p>We will send reset instructions if the account exists.</p></div>
    <label>Email<input type="email" required value={email} onChange={(event) => setEmail(event.target.value)} placeholder="you@example.com" /></label>
    <button type="submit" disabled={loading} className="primary-button">{loading ? "Sending..." : "Send Reset Link"}</button>
    {message && <span className="login-success">{message}</span>}
    <p className="secondary-text"><Link to="/login">Go to Login</Link></p>
  </form></main>;
}

export default ForgotPassword;