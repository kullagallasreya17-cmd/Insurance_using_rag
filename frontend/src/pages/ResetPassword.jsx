import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import api from "../api";
import "./Login.css";

function ResetPassword() {
  const [params] = useSearchParams();
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);

  const submit = async (event) => {
    event.preventDefault();
    if (password !== confirmPassword) { setMessage("Passwords do not match."); return; }
    if (password.length < 8 || !/[A-Za-z]/.test(password) || !/\d/.test(password)) { setMessage("Password must be at least 8 characters and include a letter and a number."); return; }
    setLoading(true);
    try {
      const response = await api.post("/auth/reset-password", { token: params.get("token"), password, confirm_password: confirmPassword });
      setMessage(response.data.message);
    } catch (error) { setMessage(error.response?.data?.detail || "This reset link is invalid or has expired."); }
    finally { setLoading(false); }
  };

  return <main className="login-page"><form className="login-panel" onSubmit={submit}>
    <div className="brand-headline"><h1>Create New Password</h1><p>Choose a strong password for your account.</p></div>
    <label>New Password<input type="password" required value={password} onChange={(event) => setPassword(event.target.value)} /></label>
    <label>Confirm Password<input type="password" required value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} /></label>
    {!message.includes("successfully") && <button type="submit" disabled={loading || !params.get("token")} className="primary-button">{loading ? "Resetting..." : "Reset Password"}</button>}
    {message && <span className={message.includes("successfully") ? "login-success" : "login-message"}>{message}</span>}
    {message.includes("successfully") && <p className="secondary-text"><Link to="/login">Go to Login</Link></p>}
  </form></main>;
}

export default ResetPassword;