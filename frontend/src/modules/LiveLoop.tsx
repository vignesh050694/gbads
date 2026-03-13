import { useEffect } from "react";

import { FeatureStatusBadge, Spinner } from "../components/Shared";
import { useAppStore } from "../store/appStore";

interface LiveLoopProps {
  featureId: string;
  onBackToProject: () => void;
}

export default function LiveLoop({
  featureId,
  onBackToProject,
}: LiveLoopProps): JSX.Element {
  const feature = useAppStore((s) => s.selectedFeature);
  const fetchFeatureDetail = useAppStore((s) => s.fetchFeatureDetail);

  useEffect(() => {
    fetchFeatureDetail(featureId).catch(() => undefined);

    const poll = setInterval(async () => {
      const next = await fetchFeatureDetail(featureId);
      if (
        next.status === "DONE" ||
        next.status === "PARTIAL" ||
        next.status === "CANCELLED"
      ) {
        clearInterval(poll);
      }
    }, 3000);

    return () => clearInterval(poll);
  }, [featureId, fetchFeatureDetail]);

  if (!feature || feature.id !== featureId) {
    return (
      <div className="max-w-4xl mx-auto px-6 py-10 text-gray-400">
        Loading loop...
      </div>
    );
  }

  const isDone = feature.status === "DONE" || feature.status === "PARTIAL";

  return (
    <div className="max-w-4xl mx-auto px-6 py-10">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h2 className="text-xl font-bold">Building: {feature.title}</h2>
          {feature.feature_branch && (
            <p className="text-sm text-gray-500 font-mono mt-1">
              {feature.feature_branch}
            </p>
          )}
        </div>
        <FeatureStatusBadge status={feature.status} large />
      </div>

      {!isDone && (
        <div className="text-center py-10">
          <Spinner />
          <p className="mt-4 text-cyan-400 animate-pulse">
            Running autonomous development loop...
          </p>
        </div>
      )}

      {isDone && (
        <div
          className={`rounded-2xl p-6 mb-6 ${feature.status === "DONE" ? "bg-green-900/30 border border-green-800" : "bg-amber-900/30 border border-amber-800"}`}
        >
          {feature.status === "DONE" ? (
            <p className="text-green-300 text-lg font-semibold">
              Task completed successfully
            </p>
          ) : (
            <p className="text-amber-300 text-lg font-semibold">
              Best effort result
            </p>
          )}
          {feature.feature_branch && (
            <p className="text-sm text-gray-400 mt-2">
              Pushed to:{" "}
              <span className="text-cyan-400">{feature.feature_branch}</span>
            </p>
          )}
        </div>
      )}

      <button
        onClick={onBackToProject}
        className="bg-gray-800 hover:bg-gray-700 text-white px-4 py-2 rounded-lg text-sm font-medium"
      >
        Back to Project
      </button>
    </div>
  );
}
