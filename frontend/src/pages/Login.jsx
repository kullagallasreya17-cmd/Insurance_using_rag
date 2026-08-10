import { useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "../api";
import { setSession } from "../auth";
import "./Login.css";

function Login() {
  const navigate = useNavigate();
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("admin123");
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);

  const login = async (event) => {
    event.preventDefault();
    setLoading(true);
    setMessage("");

    try {
      const response = await api.post("/auth/login", { username, password });
      setSession(response.data.access_token, response.data.user);
      navigate("/dashboard");
    } catch (error) {
      setMessage(error.response?.data?.detail || "Login failed.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="login-page">
      <form className="login-panel" onSubmit={login}>
        <h1>Enterprise Insurance AI</h1>
        <p>Secure access for claim teams and agents.</p>

        <label>
          Username
          <input value={username} onChange={(event) => setUsername(event.target.value)} />
        </label>

        <label>
          Password
          <input
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
        </label>

        <button type="submit" disabled={loading}>
          {loading ? "Signing in..." : "Sign In"}
        </button>

        {message && <span className="login-message">{message}</span>}
      </form>
    </main>
  );
}

export default Login;
