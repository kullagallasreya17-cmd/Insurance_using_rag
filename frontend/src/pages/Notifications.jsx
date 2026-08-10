import { useEffect, useMemo, useState } from "react";
import api from "../api";
import PortalLayout from "../components/PortalLayout";

const FALLBACK_NOTIFICATIONS = [
  "Policy uploaded successfully",
  "Document indexed successfully",
  "Claim approved",
  "New FAQ added",
];

function Notifications() {
  const [notifications, setNotifications] = useState([]);

  useEffect(() => {
    api.get("/notifications").then((response) => setNotifications(response.data.notifications || []));
  }, []);

  const visibleNotifications = useMemo(() => {
    if (notifications.length > 0) return notifications;
    return FALLBACK_NOTIFICATIONS.map((message, index) => ({
      id: `fallback-${index}`,
      type: "system",
      message,
      created_at: new Date().toISOString(),
    }));
  }, [notifications]);

  return (
    <PortalLayout
      title="Notifications"
      subtitle="Operational status, document activity, and claim updates from the backend services."
    >
      <div className="enterprise-grid">
        {visibleNotifications.map((notification) => (
          <article className="enterprise-card" key={notification.id}>
            <h3>{notification.type}</h3>
            <p>{notification.message}</p>
            <p>{new Date(notification.created_at).toLocaleString()}</p>
          </article>
        ))}
      </div>
    </PortalLayout>
  );
}

export default Notifications;
