import { useEffect, useState } from "react";
import api from "../api";
import PortalLayout from "../components/PortalLayout";

function Profile() {
  const [profile, setProfile] = useState(null);

  useEffect(() => {
    api.get("/profile").then((response) => setProfile(response.data));
  }, []);

  return (
    <PortalLayout title="User Profile" subtitle="Authenticated user details, activity, and permissions.">
      {!profile && <div className="enterprise-card">Loading profile...</div>}
      {profile && (
        <div className="enterprise-grid">
          <article className="enterprise-card">
            <h3>Account Details</h3>
            <p><strong>Username:</strong> {profile.user.username}</p>
            <p><strong>Role:</strong> {profile.user.role}</p>
            <p><strong>Email:</strong> {profile.user.email || "Not available in current backend profile model"}</p>
            <p><strong>Last Login:</strong> {profile.user.last_login || "Not tracked in current backend profile model"}</p>
          </article>

          <article className="enterprise-card">
            <h3>Activity Summary</h3>
            <p>Documents Uploaded: {profile.activity.documents_uploaded}</p>
            <p>Claims Created: {profile.activity.claims_created}</p>
          </article>

          <article className="enterprise-card">
            <h3>Permissions</h3>
            <ul>
              {profile.permissions.map((permission) => (
                <li key={permission}>{permission}</li>
              ))}
            </ul>
          </article>
        </div>
      )}
    </PortalLayout>
  );
}

export default Profile;
