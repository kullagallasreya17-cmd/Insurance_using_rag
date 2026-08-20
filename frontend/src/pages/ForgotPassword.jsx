import { useState } from "react";
import { Link } from "react-router-dom";
import api from "../api";
import "./Login.css";

export default function ForgotPassword() {
  const [email, setEmail] = useState("");
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);
  const submit = async (event) => {
    event.preventDefault(); setLoading(true); setMessage("");
    try { const response = await api.post("/auth/forgot-password", { email }); setMessage(response.data.message); }
    catch { setMessage("If an account exists for this email, password reset instructions have been sent."); }
    finally { setLoading(false); }
  };
  return <main className="login-page"><form className="login-panel" onSubmit={submit}><div className="brand-headline"><h1>Forgot Password</h1><p>Enter your email to receive reset instructions.</p></div><label>Email<input type="email" required value={email} onChange={(event) => setEmail(event.target.value)} placeholder="Enter your email address" /></label><button className="primary-button" disabled={loading}>{loading ? "Sending..." : "Send Reset Link"}</button>{message && <span className="login-message">{message}</span>}<p className="secondary-text"><Link to="/login">Back to Login</Link></p></form></main>;
}