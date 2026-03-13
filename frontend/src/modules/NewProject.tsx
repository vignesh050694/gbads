import { useState } from "react";

import { Field } from "../components/Shared";
import { useAppStore } from "../store/appStore";

interface NewProjectProps {
  onBack: () => void;
  onProjectCreated: (projectId: string) => void;
}

export default function NewProject({
  onBack,
  onProjectCreated,
}: NewProjectProps): JSX.Element {
  const createProject = useAppStore((s) => s.createProject);

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [url, setUrl] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(
    e: React.FormEvent<HTMLFormElement>,
  ): Promise<void> {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const data = await createProject({
        name,
        description,
        github_urls: [url],
        repo_structure: "MONO",
      });
      onProjectCreated(data.project_id);
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Failed to create project";
      setError(message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="max-w-2xl mx-auto px-6 py-10">
      <button
        onClick={onBack}
        className="text-gray-500 hover:text-gray-300 text-sm mb-6"
      >
        Back
      </button>
      <h2 className="text-2xl font-bold mb-6">New Project</h2>
      <form onSubmit={handleSubmit} className="space-y-4">
        <Field label="Project Name">
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
            className="w-full bg-gray-800 rounded-lg px-4 py-2 text-white border border-gray-700 focus:outline-none focus:border-cyan-500"
          />
        </Field>
        <Field label="Description">
          <input
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            className="w-full bg-gray-800 rounded-lg px-4 py-2 text-white border border-gray-700 focus:outline-none focus:border-cyan-500"
          />
        </Field>
        <Field label="GitHub Repository URL">
          <input
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            required
            placeholder="https://github.com/org/repo"
            className="w-full bg-gray-800 rounded-lg px-4 py-2 text-white border border-gray-700 focus:outline-none focus:border-cyan-500"
          />
        </Field>
        {error && <p className="text-red-400 text-sm">{error}</p>}
        <button
          type="submit"
          disabled={loading}
          className="w-full bg-cyan-600 hover:bg-cyan-500 disabled:opacity-50 text-white font-semibold py-3 rounded-xl"
        >
          {loading ? "Creating..." : "Create Project"}
        </button>
      </form>
    </div>
  );
}
