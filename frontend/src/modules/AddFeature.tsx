import { useEffect, useState } from "react";

import { Field, Spinner } from "../components/Shared";
import { useAppStore } from "../store/appStore";

interface AddFeatureProps {
  projectId: string;
  onBack: () => void;
  onReadyForMetricApproval: (featureId: string) => void;
}

export default function AddFeature({
  projectId,
  onBack,
  onReadyForMetricApproval,
}: AddFeatureProps): JSX.Element {
  const createFeature = useAppStore((s) => s.createFeature);
  const fetchFeatureDetail = useAppStore((s) => s.fetchFeatureDetail);
  const clarifyFeature = useAppStore((s) => s.clarifyFeature);
  const generateMetricPlan = useAppStore((s) => s.generateMetricPlan);

  const [title, setTitle] = useState("");
  const [requirement, setRequirement] = useState("");
  const [featureId, setFeatureId] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [clarifyQuestions, setClarifyQuestions] = useState<string[]>([]);
  const [clarifyAnswers, setClarifyAnswers] = useState<Record<string, string>>(
    {},
  );

  async function handleSubmit(
    e: React.FormEvent<HTMLFormElement>,
  ): Promise<void> {
    e.preventDefault();
    const data = await createFeature(projectId, {
      title,
      raw_requirement: requirement,
    });
    setFeatureId(data.feature_id);
    setStatus("INTERCEPTING");
  }

  useEffect(() => {
    if (!featureId) return;

    const poll = setInterval(async () => {
      const feature = await fetchFeatureDetail(featureId);
      setStatus(feature.status);

      const questions = feature.module_spec?.clarifying_questions || [];
      if (feature.status === "AWAITING_CLARIFICATION" && questions.length > 0) {
        setClarifyQuestions(questions);
        clearInterval(poll);
      }

      if (feature.status === "AWAITING_METRIC_APPROVAL") {
        clearInterval(poll);
        await generateMetricPlan(featureId);
        onReadyForMetricApproval(featureId);
      }

      if (feature.status === "CANCELLED") {
        clearInterval(poll);
      }
    }, 2000);

    return () => clearInterval(poll);
  }, [
    featureId,
    fetchFeatureDetail,
    generateMetricPlan,
    onReadyForMetricApproval,
  ]);

  async function handleClarify(
    e: React.FormEvent<HTMLFormElement>,
  ): Promise<void> {
    e.preventDefault();
    if (!featureId) return;

    await clarifyFeature(featureId, clarifyAnswers);
    setClarifyQuestions([]);
    setStatus("INTERCEPTING");
  }

  if (!featureId) {
    return (
      <div className="max-w-2xl mx-auto px-6 py-10">
        <button
          onClick={onBack}
          className="text-gray-500 hover:text-gray-300 text-sm mb-6"
        >
          Back
        </button>
        <h2 className="text-2xl font-bold mb-6">Add Feature</h2>
        <form onSubmit={handleSubmit} className="space-y-4">
          <Field label="Feature Title">
            <input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              required
              className="w-full bg-gray-800 rounded-lg px-4 py-2 text-white border border-gray-700 focus:outline-none focus:border-cyan-500"
            />
          </Field>
          <Field label="Requirement">
            <textarea
              value={requirement}
              onChange={(e) => setRequirement(e.target.value)}
              required
              rows={5}
              placeholder="Describe what you want to build..."
              className="w-full bg-gray-800 rounded-lg px-4 py-2 text-white border border-gray-700 focus:outline-none focus:border-cyan-500"
            />
          </Field>
          <button
            type="submit"
            className="w-full bg-cyan-600 hover:bg-cyan-500 text-white font-semibold py-3 rounded-xl"
          >
            Analyze Requirement
          </button>
        </form>
      </div>
    );
  }

  if (clarifyQuestions.length > 0) {
    return (
      <div className="max-w-2xl mx-auto px-6 py-10">
        <h2 className="text-2xl font-bold mb-2">Clarification Needed</h2>
        <p className="text-gray-400 mb-6">
          Please answer these questions to proceed:
        </p>
        <form onSubmit={handleClarify} className="space-y-4">
          {clarifyQuestions.map((q) => (
            <Field key={q} label={q}>
              <input
                value={clarifyAnswers[q] || ""}
                onChange={(e) =>
                  setClarifyAnswers((prev) => ({
                    ...prev,
                    [q]: e.target.value,
                  }))
                }
                className="w-full bg-gray-800 rounded-lg px-4 py-2 text-white border border-gray-700 focus:outline-none focus:border-cyan-500"
              />
            </Field>
          ))}
          <button
            type="submit"
            className="w-full bg-cyan-600 hover:bg-cyan-500 text-white font-semibold py-3 rounded-xl"
          >
            Continue
          </button>
        </form>
      </div>
    );
  }

  return (
    <div className="max-w-2xl mx-auto px-6 py-10 text-center">
      <Spinner />
      <p className="mt-4 text-cyan-400 animate-pulse">
        Analyzing requirement...
      </p>
      <p className="text-xs text-gray-500 mt-2">Status: {status}</p>
    </div>
  );
}
