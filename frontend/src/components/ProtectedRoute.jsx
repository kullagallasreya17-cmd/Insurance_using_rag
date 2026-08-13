import { Navigate, useLocation } from "react-router-dom";
import { getUser, isAuthenticated } from "../auth";

function allowedRole(userRole, requiredRole) {
  if (!requiredRole) {
    return true;
  }

  const allowed = Array.isArray(requiredRole) ? requiredRole : [requiredRole];
  return allowed.map((role) => role.toLowerCase()).includes(userRole.toLowerCase());
}

function ProtectedRoute({ children, requiredRole, requiredRoles }) {
  const location = useLocation();

  if (!isAuthenticated()) {
    return <Navigate to="/login" replace state={{ from: location }} />;
  }

  const user = getUser();
  const role = (user?.role || "").toLowerCase();
  const allowedRoles = requiredRoles || requiredRole;

  if (!allowedRole(role, allowedRoles)) {
    return <Navigate to="/dashboard" replace />;
  }

  return children;
}

export default ProtectedRoute;
