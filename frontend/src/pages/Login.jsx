import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import api from "../api";
import { setSession } from "../auth";
import "./Login.css";

function Login() {
  const navigate = useNavigate();
  const [usernameOrEmail, setUsernameOrEmail] = useState("");
  const [password, setPassword] = useState("");
  const [selectedRole, setSelectedRole] = useState("customer");
  const [showPassword, setShowPassword] = useState(false);
  const [rememberMe, setRememberMe] = useState(true);
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);

  const login = async (event) => {
    event.preventDefault();
    setMessage("");

    if (!usernameOrEmail.trim() || !password.trim()) {
      setMessage("Please enter both username/email and password.");
      return;
    }

    setLoading(true);

    try {
      const response = await api.post("/auth/login", {
        username: usernameOrEmail,
        password,
        role: selectedRole,
      });
      setSession(response.data.access_token, response.data.user, rememberMe);
      const role = response.data.user?.role?.toLowerCase();
      navigate(role === "admin" ? "/admin" : "/dashboard");
    } catch (error) {
      setMessage(error.response?.data?.detail || "Invalid credentials. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  const handleForgotPassword = (event) => {
    event.preventDefault();
    setMessage("Please contact your administrator to reset your password.");
  };

  return (
    <main className="login-page">
      <form className="login-panel" onSubmit={login}>
        <div className="brand-headline">
          <h1>Insurance AI Platform</h1>
          <p>Enterprise access for claims, policies, and analytics.</p>
        </div>

        <label>
          Username or Email
          <input
            type="text"
            value={usernameOrEmail}
            onChange={(event) => setUsernameOrEmail(event.target.value)}
            placeholder="Enter your username or email"
          />
        </label>

        <label>
          Password
          <div className="password-field">
            <input
              type={showPassword ? "text" : "password"}
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              placeholder="Enter your password"
            />
            <button
              type="button"
              className="toggle-password"
              onClick={() => setShowPassword((current) => !current)}
            >
              {showPassword ? "Hide" : "Show"}
            </button>
          </div>
        </label>

        <label>
          Role
          <select value={selectedRole} onChange={(event) => setSelectedRole(event.target.value)}>
            <option value="customer">Customer</option>
            <option value="admin">Admin</option>
            <option value="auditor">Auditor</option>
          </select>
        </label>

        <div className="form-row">
          <label className="inline-checkbox">
            <input
              type="checkbox"
              checked={rememberMe}
              onChange={(event) => setRememberMe(event.target.checked)}
            />
            Remember Me
          </label>
          <button className="text-link" onClick={handleForgotPassword}>
            Forgot Password?
          </button>
        </div>

        <button type="submit" disabled={loading} className="primary-button">
          {loading ? "Signing in..." : "Login"}
        </button>

        <p className="secondary-text">
          Don't have an account? <Link to="/register">Create Account</Link>
        </p>

        {message && <span className="login-message">{message}</span>}
      </form>
    </main>
  );
}

export default Login;
