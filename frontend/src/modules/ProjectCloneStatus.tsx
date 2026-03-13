import { useEffect, useMemo, useState } from "react";

import { Badge, CloneStatusBadge, Spinner } from "../components/Shared";
import { useAppStore } from "../store/appStore";
import type { ProjectDetail } from "../types/models";

interface ProjectCloneStatusProps {
  projectId: string;
  onReady: () => void;
}

export default function ProjectCloneStatus({
  projectId,
  onReady,
}: ProjectCloneStatusProps): JSX.Element {
  const fetchProjectDetail = useAppStore((s) => s.fetchProjectDetail);
  const [project, setProject] = useState<ProjectDetail | null>(null);

  useEffect(() => {
    const poll = setInterval(async () => {
      try {
        const data = await fetchProjectDetail(projectId);
        setProject(data);

        const allDone = (data.repos || []).every(
          (r) => r.clone_status === "DONE" || r.clone_status === "FAILED",
        );
        if (allDone && data.generated_compose) {
          clearInterval(poll);
          onReady();
        }
      } catch {
        clearInterval(poll);
      }
    }, 2000);

    return () => clearInterval(poll);
  }, [fetchProjectDetail, onReady, projectId]);

  const allDone = useMemo(
    () =>
      !!project &&
      (project.repos || []).every(
        (r) => r.clone_status === "DONE" || r.clone_status === "FAILED",
      ),
    [project],
  );

  if (!project) {
    return (
      <div className="max-w-2xl mx-auto px-6 py-10">
        <Spinner />
      </div>
    );
  }

  return (
    <div className="max-w-2xl mx-auto px-6 py-10">
      <h2 className="text-2xl font-bold mb-6">{project.name}</h2>
      {(project.repos || []).map((repo) => (
        <div key={repo.id} className="bg-gray-900 rounded-xl p-4 mb-4">
          <div className="flex items-center justify-between">
            <span className="font-medium">{repo.repo_name}</span>
            <CloneStatusBadge status={repo.clone_status} />
          </div>
        </div>
      ))}

      {allDone && !project.generated_compose && (
        <p className="text-cyan-400 text-sm animate-pulse mt-2">
          AI is analyzing codebase and writing sandbox config...
        </p>
      )}

      {allDone && project.generated_compose && (
        <div className="mt-4">
          <p className="text-green-400 text-sm mb-4">
            Ready: sandbox config generated
          </p>
          {project.detected_stack && (
            <div className="flex gap-2 flex-wrap mb-4">
              {(project.detected_stack.databases || []).map((d) => (
                <Badge key={d} label={d} icon="DB" color="blue" />
              ))}
              {(project.detected_stack.queues || []).map((q) => (
                <Badge key={q} label={q} icon="Q" color="purple" />
              ))}
            </div>
          )}
          <button
            onClick={onReady}
            className="bg-cyan-600 hover:bg-cyan-500 text-white font-semibold px-6 py-3 rounded-xl"
          >
            View Project
          </button>
        </div>
      )}
    </div>
  );
}
