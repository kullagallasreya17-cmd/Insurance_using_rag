import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import api from "../api";
import "./Login.css";

function VerifyEmail() {
  const [params] = useSearchParams();
  const [message, setMessage] = useState("Verifying your email...");
  useEffect(() => {
    api.post("/auth/verify-email", { token: params.get("token") })
      .then((response) => setMessage(response.data.message))
      .catch((error) => setMessage(error.response?.data?.detail || "This verification link is invalid or has expired."));
  }, [params]);
  return <main className="login-page"><section className="login-panel"><div className="brand-headline"><h1>Email Verification</h1><p className={message.includes("successfully") ? "login-success" : "login-message"}>{message}</p></div><p className="secondary-text"><Link to="/login">Go to Login</Link></p></section></main>;
}

export default VerifyEmail;