import { Link, useLocation, useNavigate } from "react-router-dom";
import { clearSession } from "../auth";
import "./Sidebar.css";

function Sidebar() {
  const location = useLocation();
  const navigate = useNavigate();

  const menuItems = [
    { name: "Dashboard", path: "/dashboard", icon: "DB" },
    { name: "Upload Policy", path: "/upload-policy", icon: "UP" },
    { name: "Documents", path: "/documents", icon: "DC" },
    { name: "Policies", path: "/policies", icon: "PL" },
    { name: "AI Chatbot", path: "/chatbot", icon: "AI" },
    { name: "Claim Analysis & Claims", path: "/claim-analysis", icon: "CA" },
    { name: "Analytics", path: "/analytics", icon: "AN" },
    { name: "Notifications", path: "/notifications", icon: "NT" },
    { name: "Profile", path: "/profile", icon: "PR" },
    { name: "Settings", path: "/settings", icon: "ST" },
    { name: "Admin", path: "/admin", icon: "AD" },
  ];

  const logout = () => {
    clearSession();
    navigate("/login");
  };

  return (
    <div className="sidebar">
      <div className="logo">
        <h2>Insurance AI</h2>
      </div>

      <ul className="menu">
        {menuItems.map((item) => (
          <li key={item.name} className={location.pathname === item.path ? "active" : ""}>
            <Link to={item.path}>
              <span>{item.icon}</span>
              {item.name}
            </Link>
          </li>
        ))}
      </ul>

      <div className="logout">
        <button onClick={logout}>Logout</button>
      </div>
    </div>
  );
}

export default Sidebar;
