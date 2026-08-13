import { Link, useLocation, useNavigate } from "react-router-dom";
import { clearSession, getUser } from "../auth";
import "./Sidebar.css";

function Sidebar() {
  const location = useLocation();
  const navigate = useNavigate();
  const user = getUser() || {};
  const role = (user.role || "agent").toLowerCase();

  const menuItems = [
    { name: "Dashboard", path: "/dashboard", icon: "DB", roles: ["admin", "analyst", "agent", "auditor"] },
    { name: "Upload Policy", path: "/upload-policy", icon: "UP", roles: ["admin", "agent"] },
    { name: "Documents", path: "/documents", icon: "DC", roles: ["admin", "analyst", "agent", "auditor"] },
    { name: "Policies", path: "/policies", icon: "PL", roles: ["admin", "analyst", "agent", "auditor"] },
    { name: "AI Chatbot", path: "/chatbot", icon: "AI", roles: ["admin", "analyst", "agent", "auditor"] },
    { name: "Claim Analysis & Claims", path: "/claim-analysis", icon: "CA", roles: ["admin", "analyst", "agent", "auditor"] },
    { name: "Analytics", path: "/analytics", icon: "AN", roles: ["admin", "analyst", "auditor"] },
    { name: "Notifications", path: "/notifications", icon: "NT", roles: ["admin", "analyst", "agent", "auditor"] },
    { name: "Profile", path: "/profile", icon: "PR", roles: ["admin", "analyst", "agent", "auditor"] },
    { name: "Settings", path: "/settings", icon: "ST", roles: ["admin", "analyst", "agent", "auditor"] },
    { name: "Admin", path: "/admin", icon: "AD", roles: ["admin"] },
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
        {menuItems
          .filter((item) => item.roles.includes(role))
          .map((item) => (
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
