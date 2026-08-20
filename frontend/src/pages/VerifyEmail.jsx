import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import api from "../api";
import "./Login.css";

export default function VerifyEmail() {
  const [params] = useSearchParams(); const token = params.get("token") || ""; const [message, setMessage] = useState("Verifying your email...");
  useEffect(() => { api.post("/auth/verify-email", { token }).then((response) => setMessage(response.data.message)).catch((error) => setMessage(error.response?.data?.detail || "This verification link is invalid or expired.")); }, [token]);
  return <main className="login-page"><div className="login-panel"><div className="brand-headline"><h1>Email Verification</h1><p>{message}</p></div><p className="secondary-text"><Link to="/login">Go to Login</Link></p></div></main>;
}