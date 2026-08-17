import { Link, useLocation, useNavigate } from "react-router-dom";
import { clearSession, getUser } from "../auth";
import "./Sidebar.css";

function Sidebar() {
  const location = useLocation();
  const navigate = useNavigate();
  const user = getUser() || {};
  const role = (user.role || "admin").toLowerCase();

  const menuItems = [
    { name: "Dashboard", path: "/dashboard", icon: "DB", roles: ["admin"] },
    { name: "Upload Policy", path: "/upload-policy", icon: "UP", roles: ["admin"] },
    { name: "Documents", path: "/documents", icon: "DC", roles: ["admin"] },
    { name: "Policies", path: "/policies", icon: "PL", roles: ["admin"] },
    { name: "AI Chatbot", path: "/chatbot", icon: "AI", roles: ["admin"] },
    { name: "Claim Analysis & Claims", path: "/claim-analysis", icon: "CA", roles: ["admin"] },
    { name: "Analytics", path: "/analytics", icon: "AN", roles: ["admin"] },
    { name: "Notifications", path: "/notifications", icon: "NT", roles: ["admin"] },
    { name: "Profile", path: "/profile", icon: "PR", roles: ["admin"] },
    { name: "Settings", path: "/settings", icon: "ST", roles: ["admin"] },
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
