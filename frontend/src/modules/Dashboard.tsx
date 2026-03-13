import { useEffect } from "react";

import { Badge, Spinner } from "../components/Shared";
import { useAppStore } from "../store/appStore";
import type { ProjectSummary } from "../types/models";

interface DashboardProps {
  onOpenProject: (projectId: string) => void;
  onNewProject: () => void;
}

function ProjectCard({
  project,
  onClick,
}: {
  project: ProjectSummary;
  onClick: () => void;
}): JSX.Element {
  const stack = project.detected_stack || {};
  const dbs = stack.databases || [];
  const queues = stack.queues || [];

  return (
    <button
      onClick={onClick}
      className="bg-gray-900 hover:bg-gray-800 rounded-xl p-6 text-left transition border border-gray-800 hover:border-gray-700"
    >
      <h3 className="font-semibold text-lg">{project.name}</h3>
      <p className="text-sm text-gray-400 mt-1 mb-3">{project.description}</p>
      <div className="flex flex-wrap gap-2">
        {dbs.map((d) => (
          <Badge key={d} label={d} icon="DB" color="blue" />
        ))}
        {queues.map((q) => (
          <Badge key={q} label={q} icon="Q" color="purple" />
        ))}
        {stack.language && (
          <Badge label={stack.language} icon="TS" color="green" />
        )}
      </div>
      <p className="text-xs text-gray-600 mt-3">View Project</p>
    </button>
  );
}

export default function Dashboard({
  onOpenProject,
  onNewProject,
}: DashboardProps): JSX.Element {
  const me = useAppStore((s) => s.me);
  const projects = useAppStore((s) => s.projects);
  const loading = useAppStore((s) => s.loading);
  const error = useAppStore((s) => s.error);
  const fetchProjects = useAppStore((s) => s.fetchProjects);
  const fetchMe = useAppStore((s) => s.fetchMe);
  const logout = useAppStore((s) => s.logout);

  useEffect(() => {
    fetchProjects().catch(() => undefined);
    fetchMe().catch(() => undefined);
  }, [fetchMe, fetchProjects]);

  return (
    <div className="max-w-5xl mx-auto px-6 py-10">
      <header className="flex items-center justify-between mb-10">
        <h1 className="text-2xl font-bold text-cyan-400">GBADS</h1>
        {me && (
          <div className="flex items-center gap-3">
            {me.avatar_url && (
              <img
                src={me.avatar_url}
                className="w-8 h-8 rounded-full"
                alt=""
              />
            )}
            <span className="text-sm text-gray-400">@{me.github_username}</span>
            <button
              onClick={logout}
              className="text-xs text-gray-600 hover:text-gray-400"
            >
              Logout
            </button>
          </div>
        )}
      </header>

      <div className="flex items-center justify-between mb-6">
        <h2 className="text-xl font-semibold">Projects</h2>
        <button
          onClick={onNewProject}
          className="bg-cyan-600 hover:bg-cyan-500 text-white px-4 py-2 rounded-lg text-sm font-medium"
        >
          + New Project
        </button>
      </div>

      {error && <p className="text-red-400 text-sm mb-4">{error}</p>}

      {loading ? (
        <Spinner />
      ) : projects.length === 0 ? (
        <div className="text-center text-gray-500 py-20">
          <p>No projects yet.</p>
          <button
            onClick={onNewProject}
            className="mt-4 text-cyan-400 hover:underline"
          >
            Create your first project
          </button>
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {projects.map((p) => (
            <ProjectCard
              key={p.id}
              project={p}
              onClick={() => onOpenProject(p.id)}
            />
          ))}
        </div>
      )}
    </div>
  );
}
