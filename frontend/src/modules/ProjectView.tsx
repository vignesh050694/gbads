import { useEffect, useMemo } from "react";

import { FeatureStatusBadge } from "../components/Shared";
import { useAppStore } from "../store/appStore";
import type { FeatureSummary } from "../types/models";

interface ProjectViewProps {
  projectId: string;
  onBack: () => void;
  onAddFeature: () => void;
  onOpenFeature: (featureId: string, status: string) => void;
}

function FeatureRow({
  feature,
  onOpen,
}: {
  feature: FeatureSummary;
  onOpen: (featureId: string, status: string) => void;
}): JSX.Element {
  return (
    <div className="bg-gray-900 rounded-xl p-5 flex items-center justify-between">
      <div>
        <span className="font-medium">{feature.title}</span>
        {feature.feature_branch && (
          <span className="ml-3 text-xs text-gray-500 font-mono">
            {feature.feature_branch}
          </span>
        )}
      </div>
      <div className="flex items-center gap-4">
        <FeatureStatusBadge status={feature.status} />
        <button
          onClick={() => onOpen(feature.id, feature.status)}
          className="text-sm text-cyan-400 hover:underline"
        >
          View
        </button>
      </div>
    </div>
  );
}

export default function ProjectView({
  projectId,
  onBack,
  onAddFeature,
  onOpenFeature,
}: ProjectViewProps): JSX.Element {
  const selectedProject = useAppStore((s) => s.selectedProject);
  const fetchProjectDetail = useAppStore((s) => s.fetchProjectDetail);

  useEffect(() => {
    fetchProjectDetail(projectId).catch(() => undefined);
  }, [fetchProjectDetail, projectId]);

  const project = useMemo(() => selectedProject, [selectedProject]);

  if (!project) {
    return (
      <div className="max-w-5xl mx-auto px-6 py-10 text-gray-400">
        Loading project...
      </div>
    );
  }

  return (
    <div className="max-w-5xl mx-auto px-6 py-10">
      <button
        onClick={onBack}
        className="text-gray-500 hover:text-gray-300 text-sm mb-6"
      >
        Dashboard
      </button>
      <div className="flex items-center justify-between mb-8">
        <div>
          <h2 className="text-2xl font-bold">{project.name}</h2>
          <p className="text-gray-400 text-sm">{project.description}</p>
        </div>
        <button
          onClick={onAddFeature}
          className="bg-cyan-600 hover:bg-cyan-500 text-white px-4 py-2 rounded-lg text-sm font-medium"
        >
          + Add Feature
        </button>
      </div>

      {(project.features || []).length === 0 ? (
        <div className="text-center text-gray-500 py-20">
          <p>No features yet.</p>
          <button
            onClick={onAddFeature}
            className="mt-4 text-cyan-400 hover:underline"
          >
            Add your first feature
          </button>
        </div>
      ) : (
        <div className="space-y-3">
          {(project.features || []).map((f) => (
            <FeatureRow key={f.id} feature={f} onOpen={onOpenFeature} />
          ))}
        </div>
      )}
    </div>
  );
}
