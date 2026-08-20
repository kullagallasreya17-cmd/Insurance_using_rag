import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import api from "../api";
import { setSession } from "../auth";
import "./Login.css";

function Register() {
  const navigate = useNavigate();
  const [form, setForm] = useState({
    full_name: "",
    username: "",
    password: "",
    confirm_password: "",
    role: "customer",
  });
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);

  const updateForm = (field, value) => {
    setForm((current) => ({ ...current, [field]: value }));
  };

  const register = async (event) => {
    event.preventDefault();
    setMessage("");

    if (!form.full_name.trim() || !form.username.trim() || !form.password.trim() || !form.confirm_password.trim()) {
      setMessage("Please complete all fields before submitting.");
      return;
    }

    if (form.password !== form.confirm_password) {
      setMessage("Passwords do not match. Please confirm your password.");
      return;
    }

    if (form.password.length < 8) {
      setMessage("Password must be at least 8 characters long.");
      return;
    }

    setLoading(true);

    try {
      const response = await api.post("/auth/register", {
        full_name: form.full_name,
        username: form.username,
        password: form.password,
        role: form.role,
      });
      setSession(response.data.access_token, response.data.user);
      navigate("/dashboard");
    } catch (error) {
      setMessage(error.response?.data?.detail || "Registration failed. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="login-page">
      <form className="login-panel" onSubmit={register}>
        <div className="brand-headline">
          <h1>Create Account</h1>
          <p>Set up an Insurance AI account for claims and analysis work.</p>
        </div>

        <label>
          Full Name
          <input
            type="text"
            value={form.full_name}
            onChange={(event) => updateForm("full_name", event.target.value)}
            placeholder="Enter your full name"
          />
        </label>

        <label>
          Username or Email
          <input
            type="text"
            value={form.username}
            onChange={(event) => updateForm("username", event.target.value)}
            placeholder="Enter your username or email"
          />
        </label>

        <label>
          Password
          <input
            type="password"
            value={form.password}
            onChange={(event) => updateForm("password", event.target.value)}
            placeholder="Create a password"
          />
        </label>

        <label>
          Role
          <select value={form.role} onChange={(event) => updateForm("role", event.target.value)}>
            <option value="customer">Customer</option>
            <option value="admin">Admin</option>
            <option value="auditor">Auditor</option>
          </select>
        </label>

        <label>
          Confirm Password
          <input
            type="password"
            value={form.confirm_password}
            onChange={(event) => updateForm("confirm_password", event.target.value)}
            placeholder="Confirm your password"
          />
        </label>

        <button type="submit" disabled={loading} className="primary-button">
          {loading ? "Creating account..." : "Create Account"}
        </button>

        <p className="secondary-text">
          Already have an account? <Link to="/login">Sign in</Link>
        </p>

        {message && <span className="login-message">{message}</span>}
      </form>
    </main>
  );
}

export default Register;
