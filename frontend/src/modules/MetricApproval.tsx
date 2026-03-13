import { useEffect } from "react";

import { Row } from "../components/Shared";
import { useAppStore } from "../store/appStore";

interface MetricApprovalProps {
  featureId: string;
  onBackToProject: () => void;
  onStartLiveLoop: (featureId: string) => void;
}

export default function MetricApproval({
  featureId,
  onBackToProject,
  onStartLiveLoop,
}: MetricApprovalProps): JSX.Element {
  const selectedFeature = useAppStore((s) => s.selectedFeature);
  const approveMetric = useAppStore((s) => s.approveMetric);
  const fetchFeatureDetail = useAppStore((s) => s.fetchFeatureDetail);

  useEffect(() => {
    fetchFeatureDetail(featureId).catch(() => undefined);
  }, [featureId, fetchFeatureDetail]);

  const feature =
    selectedFeature && selectedFeature.id === featureId
      ? selectedFeature
      : null;
  const plan = feature?.benchmark_plan;

  if (!feature) {
    return (
      <div className="max-w-2xl mx-auto px-6 py-10 text-gray-400">
        Loading feature...
      </div>
    );
  }

  if (!plan) {
    return (
      <div className="max-w-2xl mx-auto px-6 py-10 text-gray-400">
        Building metric plan...
      </div>
    );
  }

  async function handleApprove(): Promise<void> {
    await approveMetric(feature.id);
    onStartLiveLoop(feature.id);
  }

  const categoryIcons: Record<string, string> = {
    happy_path: "OK",
    security: "SEC",
    boundary: "BND",
    null_input: "NIL",
    edge_case: "EDGE",
  };

  return (
    <div className="max-w-2xl mx-auto px-6 py-10">
      <div className="bg-gray-900 rounded-2xl p-8 border border-gray-800">
        <h2 className="text-xl font-bold mb-1">Metric Plan</h2>
        <p className="text-gray-400 text-sm mb-6">
          Review and approve before development begins
        </p>

        <div className="space-y-3 mb-6">
          <Row label="Metric" value={plan.metric} />
          <Row label="Formula" value={plan.formula} />
          <Row label="Target" value={plan.target} />
          <Row label="Total Tests" value={`${plan.total_planned} test cases`} />
        </div>

        <div className="mb-6">
          <p className="text-sm font-semibold text-gray-300 mb-2">
            Test breakdown:
          </p>
          <div className="space-y-1">
            {Object.entries(plan.planned_test_cases || {}).map(
              ([cat, info]) => (
                <div key={cat} className="flex items-center gap-3 text-sm">
                  <span>{categoryIcons[cat] || "*"}</span>
                  <span className="text-gray-400 w-24">
                    {cat.replace("_", " ")}
                  </span>
                  <span className="text-white font-medium">{info.count}</span>
                  <span className="text-gray-500 text-xs">
                    {(info.examples || []).slice(0, 2).join(", ")}
                  </span>
                </div>
              ),
            )}
          </div>
        </div>

        {plan.real_infra_testing && (
          <div className="bg-blue-900/30 rounded-xl p-4 mb-6 text-sm">
            <p className="text-blue-300 font-medium mb-1">
              Real infrastructure testing
            </p>
            <p className="text-blue-400">
              {(plan.infra_services || []).join(" · ")}
            </p>
            <p className="text-gray-400 text-xs mt-1">{plan.infra_note}</p>
          </div>
        )}

        <div className="flex gap-3">
          <button
            onClick={handleApprove}
            className="flex-1 bg-green-600 hover:bg-green-500 text-white font-semibold py-3 rounded-xl"
          >
            Approve & Start Development
          </button>
          <button
            onClick={onBackToProject}
            className="px-6 bg-gray-800 hover:bg-gray-700 text-white rounded-xl"
          >
            Edit
          </button>
        </div>
      </div>
    </div>
  );
}
