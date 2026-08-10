import Navbar from "./Navbar";
import Sidebar from "./Sidebar";
import "./PortalLayout.css";

function PortalLayout({ title, subtitle, children }) {
  return (
    <div className="portal-shell">
      <Sidebar />
      <main className="portal-main">
        <Navbar />
        <section className="portal-content">
          <div className="portal-heading">
            <h1>{title}</h1>
            {subtitle && <p>{subtitle}</p>}
          </div>
          {children}
        </section>
      </main>
    </div>
  );
}

export default PortalLayout;
