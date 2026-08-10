import { useEffect, useState } from "react";
import api from "../api";
import PortalLayout from "../components/PortalLayout";

function Settings() {
  const [settings, setSettings] = useState(null);

  useEffect(() => {
    api.get("/settings").then((response) => setSettings(response.data));
  }, []);

  return (
    <PortalLayout title="Settings" subtitle="Runtime security, RAG, and file-processing configuration.">
      {!settings && <div className="enterprise-card">Loading settings...</div>}
      {settings && (
        <div className="enterprise-grid">
          {Object.entries(settings).map(([section, values]) => (
            <article className="enterprise-card" key={section}>
              <h3>{section}</h3>
              {Object.entries(values).map(([key, value]) => (
                <p key={key}>
                  <strong>{key}:</strong> {Array.isArray(value) ? value.join(", ") : value}
                </p>
              ))}
            </article>
          ))}
        </div>
      )}
    </PortalLayout>
  );
}

export default Settings;
