import { useEffect, useState } from "react";
import { ProjectDashboardPage, type View } from "../features/dashboard/ProjectDashboardPage";
import { LandingPage } from "../features/landing/LandingPage";

function getInitialPage(): "dashboard" | "landing" {
  if (typeof window === "undefined") return "landing";
  const path = window.location.pathname.toLowerCase();
  const hash = window.location.hash.toLowerCase();
  if (path.startsWith("/dashboard") || hash === "#dashboard") {
    return "dashboard";
  }
  return "landing";
}

export function App() {
  const [page, setPage] = useState<"dashboard" | "landing">(getInitialPage);
  const [activeView, setActiveView] = useState<View>("reconciliation");

  useEffect(() => {
    const handlePopState = () => {
      setPage(getInitialPage());
    };
    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, []);

  const handleEnterApp = (targetView?: View) => {
    if (targetView) {
      setActiveView(targetView);
    }
    setPage("dashboard");
    if (window.location.pathname !== "/dashboard") {
      try {
        window.history.pushState(null, "", "/dashboard");
      } catch {
        // Fallback for sandboxed or restricted iframe environments
      }
    }
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const handleOpenMethodology = () => {
    setPage("landing");
    if (window.location.pathname !== "/") {
      try {
        window.history.pushState(null, "", "/");
      } catch {
        // Fallback for sandboxed or restricted iframe environments
      }
    }
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  if (page === "landing") {
    return <LandingPage onEnterApp={handleEnterApp} />;
  }

  return <ProjectDashboardPage initialView={activeView} onOpenMethodology={handleOpenMethodology} />;
}
