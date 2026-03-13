import { useMemo, useState } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import Dashboard from "./modules/Dashboard";
import LoginScreen from "./modules/LoginScreen";
import NewProject from "./modules/NewProject";
import OAuthCallback from "./modules/OAuthCallback";
import ProjectView from "./modules/ProjectView";
import AddFeature from "./modules/AddFeature";
import MetricApproval from "./modules/MetricApproval";
import LiveLoop from "./modules/LiveLoop";
import ProjectCloneStatus from "./modules/ProjectCloneStatus";
import { useAppStore } from "./store/appStore";

export default function App(): JSX.Element {
  const token = useAppStore((s) => s.token);

  return (
    <BrowserRouter>
      <div className="min-h-screen bg-gray-950 text-gray-100 font-sans">
        <Routes>
          <Route path="/oauth/callback" element={<OAuthCallback />} />
          <Route
            path="/*"
            element={token ? <AuthenticatedApp /> : <LoginScreen />}
          />
        </Routes>
      </div>
    </BrowserRouter>
  );
}

function AuthenticatedApp(): JSX.Element {
  const [projectId, setProjectId] = useState<string | null>(null);
  const [featureId, setFeatureId] = useState<string | null>(null);
  const [newProjectId, setNewProjectId] = useState<string | null>(null);
  const [screen, setScreen] = useState<
    | "dashboard"
    | "new-project"
    | "project-cloning"
    | "project"
    | "add-feature"
    | "metric-approval"
    | "live-loop"
  >("dashboard");

  const content = useMemo(() => {
    if (screen === "dashboard") {
      return (
        <Dashboard
          onNewProject={() => setScreen("new-project")}
          onOpenProject={(id) => {
            setProjectId(id);
            setScreen("project");
          }}
        />
      );
    }

    if (screen === "new-project") {
      return (
        <NewProject
          onBack={() => setScreen("dashboard")}
          onProjectCreated={(id) => {
            setNewProjectId(id);
            setScreen("project-cloning");
          }}
        />
      );
    }

    if (screen === "project-cloning" && newProjectId) {
      return (
        <ProjectCloneStatus
          projectId={newProjectId}
          onReady={() => {
            setProjectId(newProjectId);
            setScreen("project");
          }}
        />
      );
    }

    if (screen === "project" && projectId) {
      return (
        <ProjectView
          projectId={projectId}
          onBack={() => setScreen("dashboard")}
          onAddFeature={() => setScreen("add-feature")}
          onOpenFeature={(id, status) => {
            setFeatureId(id);
            if (status === "AWAITING_METRIC_APPROVAL") {
              setScreen("metric-approval");
            } else {
              setScreen("live-loop");
            }
          }}
        />
      );
    }

    if (screen === "add-feature" && projectId) {
      return (
        <AddFeature
          projectId={projectId}
          onBack={() => setScreen("project")}
          onReadyForMetricApproval={(id) => {
            setFeatureId(id);
            setScreen("metric-approval");
          }}
        />
      );
    }

    if (screen === "metric-approval" && featureId) {
      return (
        <MetricApproval
          featureId={featureId}
          onBackToProject={() => setScreen("project")}
          onStartLiveLoop={(id) => {
            setFeatureId(id);
            setScreen("live-loop");
          }}
        />
      );
    }

    if (screen === "live-loop" && featureId) {
      return (
        <LiveLoop
          featureId={featureId}
          onBackToProject={() => setScreen("project")}
        />
      );
    }

    return <Navigate to="/" replace />;
  }, [featureId, newProjectId, projectId, screen]);

  return content;
}
