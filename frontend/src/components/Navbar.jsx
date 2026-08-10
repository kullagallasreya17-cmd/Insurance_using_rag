import { getUser } from "../auth";
import { Link } from "react-router-dom";
import "./Navbar.css";

function Navbar() {
  const user = getUser();

  return (
    <header className="navbar">
      <div className="navbar-left">
        <h2>Enterprise Insurance AI Platform</h2>
      </div>

      <div className="navbar-center">
        <input
          type="text"
          placeholder="Search policies, claims..."
          className="search-box"
        />
      </div>

      <div className="navbar-right">
        <Link className="notification-btn" to="/notifications">Alerts</Link>

        <Link className="profile" to="/profile">
          <img
            src="https://i.pravatar.cc/40"
            alt="Profile"
          />
          <span>{user?.full_name || "Admin"}</span>
        </Link>
      </div>
    </header>
  );
}

export default Navbar;
