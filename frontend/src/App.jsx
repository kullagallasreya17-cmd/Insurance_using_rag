import { BrowserRouter, Route, Routes } from "react-router-dom";

import ProtectedRoute from "./components/ProtectedRoute";
import AdminDashboard from "./pages/AdminDashboard";
import Analytics from "./pages/Analytics";
import Chatbot from "./pages/Chatbot";
import ClaimAnalysis from "./pages/ClaimAnalysis";
import ClaimDetails from "./pages/ClaimDetails";
import Dashboard from "./pages/Dashboard";
import Documents from "./pages/Documents";
import ForgotPassword from "./pages/ForgotPassword";
import Landing from "./pages/Landing";
import Login from "./pages/Login";
import Notifications from "./pages/Notifications";
import Policies from "./pages/Policies";
import Profile from "./pages/Profile";
import Register from "./pages/Register";
import ResetPassword from "./pages/ResetPassword";
import VerifyEmail from "./pages/VerifyEmail";
import Settings from "./pages/Settings";
import UploadPolicy from "./pages/UploadPolicy";

import "./App.css";

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />
        <Route path="/forgot-password" element={<ForgotPassword />} />
        <Route path="/reset-password" element={<ResetPassword />} />
        <Route path="/verify-email" element={<VerifyEmail />} />
        <Route path="/dashboard" element={<ProtectedRoute><Dashboard /></ProtectedRoute>} />
        <Route path="/upload-policy" element={<ProtectedRoute requiredRoles={["admin", "customer"]}><UploadPolicy /></ProtectedRoute>} />
        <Route path="/documents" element={<ProtectedRoute><Documents /></ProtectedRoute>} />
        <Route path="/policies" element={<ProtectedRoute><Policies /></ProtectedRoute>} />
        <Route path="/claim-analysis" element={<ProtectedRoute requiredRoles={["admin", "customer"]}><ClaimAnalysis /></ProtectedRoute>} />
        <Route path="/claims" element={<ProtectedRoute requiredRoles={["admin", "customer", "auditor"]}><ClaimAnalysis /></ProtectedRoute>} />
        <Route path="/claims/:id" element={<ProtectedRoute><ClaimDetails /></ProtectedRoute>} />
        <Route path="/chatbot" element={<ProtectedRoute><Chatbot /></ProtectedRoute>} />
        <Route path="/analytics" element={<ProtectedRoute requiredRoles={["admin", "auditor"]}><Analytics /></ProtectedRoute>} />
        <Route path="/notifications" element={<ProtectedRoute><Notifications /></ProtectedRoute>} />
        <Route path="/profile" element={<ProtectedRoute><Profile /></ProtectedRoute>} />
        <Route path="/settings" element={<ProtectedRoute requiredRoles={["admin"]}><Settings /></ProtectedRoute>} />
        <Route path="/admin" element={<ProtectedRoute requiredRoles={["admin", "auditor"]}><AdminDashboard /></ProtectedRoute>} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
