import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import api from "../api";
import "./Login.css";

export default function ResetPassword() {
  const [params] = useSearchParams(); const token = params.get("token") || "";
  const [password, setPassword] = useState(""); const [confirm, setConfirm] = useState(""); const [message, setMessage] = useState(""); const [done, setDone] = useState(false);
  const submit = async (event) => { event.preventDefault(); if (password.length < 8) return setMessage("Password must be at least 8 characters long."); if (password !== confirm) return setMessage("Passwords do not match."); try { const response = await api.post("/auth/reset-password", { token, password }); setMessage(response.data.message); setDone(true); } catch (error) { setMessage(error.response?.data?.detail || "This reset link is invalid or expired."); } };
  return <main className="login-page"><form className="login-panel" onSubmit={submit}><div className="brand-headline"><h1>Create New Password</h1><p>Choose a new secure password for your account.</p></div><label>New Password<input type="password" required value={password} onChange={(event) => setPassword(event.target.value)} /></label><label>Confirm Password<input type="password" required value={confirm} onChange={(event) => setConfirm(event.target.value)} /></label>{!done && <button className="primary-button">Reset Password</button>}{message && <span className="login-message">{message}</span>}{done && <p className="secondary-text"><Link to="/login">Go to Login</Link></p>}</form></main>;
}