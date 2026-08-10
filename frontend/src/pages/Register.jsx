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
    role: "agent",
  });
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);

  const updateForm = (field, value) => {
    setForm((current) => ({ ...current, [field]: value }));
  };

  const register = async (event) => {
    event.preventDefault();
    setLoading(true);
    setMessage("");

    try {
      const response = await api.post("/auth/register", form);
      setSession(response.data.access_token, response.data.user);
      navigate("/dashboard");
    } catch (error) {
      setMessage(error.response?.data?.detail || "Registration failed.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="login-page">
      <form className="login-panel" onSubmit={register}>
        <h1>Create Account</h1>
        <p>Register a claim operations user.</p>

        <label>
          Full Name
          <input value={form.full_name} onChange={(event) => updateForm("full_name", event.target.value)} />
        </label>

        <label>
          Username
          <input value={form.username} onChange={(event) => updateForm("username", event.target.value)} />
        </label>

        <label>
          Password
          <input
            type="password"
            value={form.password}
            onChange={(event) => updateForm("password", event.target.value)}
          />
        </label>

        <label>
          Role
          <select value={form.role} onChange={(event) => updateForm("role", event.target.value)}>
            <option value="agent">Agent</option>
            <option value="analyst">Analyst</option>
            <option value="admin">Admin</option>
          </select>
        </label>

        <button type="submit" disabled={loading}>
          {loading ? "Creating..." : "Register"}
        </button>

        <Link to="/login">Already have an account?</Link>
        {message && <span className="login-message">{message}</span>}
      </form>
    </main>
  );
}

export default Register;
