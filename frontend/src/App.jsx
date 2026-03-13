/**
 * GBADS v2 Frontend — React + Tailwind CSS
 * Screens: Login → Dashboard → New Project → Feature List → Add Feature → Metric Approval → Live Loop
 */
import { useEffect, useState, useRef } from "react";

// With Vite proxy, API calls go through /auth, /projects, /features, /requirements
// For the GitHub OAuth redirect link we still need the backend origin
const API = "";

// ── API helpers ───────────────────────────────────────────────────────────────

function getToken() {
  return localStorage.getItem("gbads_token");
}

async function apiFetch(path, opts = {}) {
  const token = getToken();
  const res = await fetch(`${API}${path}`, {
    ...opts,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(opts.headers || {}),
    },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "Request failed");
  }
  return res.json();
}

// ── App root ─────────────────────────────────────────────────────────────────

export default function App() {
  const [token, setToken] = useState(localStorage.getItem("gbads_token"));
  const [screen, setScreen] = useState("dashboard");
  const [selectedProject, setSelectedProject] = useState(null);
  const [selectedFeature, setSelectedFeature] = useState(null);

  // Handle OAuth callback token in URL
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const t = params.get("token");
    if (t) {
      localStorage.setItem("gbads_token", t);
      setToken(t);
      window.history.replaceState({}, "", "/");
    }
  }, []);

  const nav = (s, project = null, feature = null) => {
    setScreen(s);
    if (project !== null) setSelectedProject(project);
    if (feature !== null) setSelectedFeature(feature);
  };

  if (!token) return <LoginScreen />;

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100 font-sans">
      {screen === "dashboard" && (
        <Dashboard nav={nav} />
      )}
      {screen === "new-project" && (
        <NewProject nav={nav} />
      )}
      {screen === "project" && selectedProject && (
        <ProjectView project={selectedProject} nav={nav} />
      )}
      {screen === "add-feature" && selectedProject && (
        <AddFeature project={selectedProject} nav={nav} />
      )}
      {screen === "metric-approval" && selectedFeature && (
        <MetricApproval feature={selectedFeature} nav={nav} />
      )}
      {screen === "live-loop" && selectedFeature && (
        <LiveLoop feature={selectedFeature} nav={nav} />
      )}
    </div>
  );
}

// ── Screen 0: Login ───────────────────────────────────────────────────────────

function LoginScreen() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-950">
      <div className="bg-gray-900 p-10 rounded-2xl shadow-xl text-center max-w-md w-full">
        <h1 className="text-3xl font-bold text-cyan-400 mb-2">GBADS</h1>
        <p className="text-gray-400 mb-8">Goal-Based Autonomous Development System</p>
        <a
          href="http://localhost:8000/auth/github"
          className="inline-flex items-center gap-3 bg-gray-800 hover:bg-gray-700 text-white font-semibold px-6 py-3 rounded-xl transition"
        >
          <GitHubIcon />
          Login with GitHub
        </a>
        <p className="text-xs text-gray-600 mt-4">Requires repo scope to clone private repos</p>
      </div>
    </div>
  );
}

// ── Screen 1: Dashboard ───────────────────────────────────────────────────────

function Dashboard({ nav }) {
  const [projects, setProjects] = useState([]);
  const [me, setMe] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([apiFetch("/projects"), apiFetch("/auth/me")])
      .then(([projs, user]) => { setProjects(projs); setMe(user); })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="max-w-5xl mx-auto px-6 py-10">
      <header className="flex items-center justify-between mb-10">
        <h1 className="text-2xl font-bold text-cyan-400">GBADS</h1>
        {me && (
          <div className="flex items-center gap-3">
            {me.avatar_url && <img src={me.avatar_url} className="w-8 h-8 rounded-full" alt="" />}
            <span className="text-sm text-gray-400">@{me.github_username}</span>
            <button
              onClick={() => { localStorage.removeItem("gbads_token"); window.location.reload(); }}
              className="text-xs text-gray-600 hover:text-gray-400"
            >Logout</button>
          </div>
        )}
      </header>

      <div className="flex items-center justify-between mb-6">
        <h2 className="text-xl font-semibold">Projects</h2>
        <button
          onClick={() => nav("new-project")}
          className="bg-cyan-600 hover:bg-cyan-500 text-white px-4 py-2 rounded-lg text-sm font-medium"
        >+ New Project</button>
      </div>

      {loading ? <Spinner /> : projects.length === 0 ? (
        <div className="text-center text-gray-500 py-20">
          <p>No projects yet.</p>
          <button onClick={() => nav("new-project")} className="mt-4 text-cyan-400 hover:underline">Create your first project</button>
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {projects.map(p => (
            <ProjectCard key={p.id} project={p} onClick={() => nav("project", p)} />
          ))}
        </div>
      )}
    </div>
  );
}

function ProjectCard({ project, onClick }) {
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
        {dbs.map(d => <Badge key={d} label={d} icon="🗄" color="blue" />)}
        {queues.map(q => <Badge key={q} label={q} icon="📨" color="purple" />)}
        {stack.language && <Badge label={stack.language} icon="⚡" color="green" />}
      </div>
      <p className="text-xs text-gray-600 mt-3">View Project →</p>
    </button>
  );
}

// ── Screen 2: New Project ─────────────────────────────────────────────────────

function NewProject({ nav }) {
  const [name, setName] = useState("");
  const [desc, setDesc] = useState("");
  const [url, setUrl] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [project, setProject] = useState(null);

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const data = await apiFetch("/projects", {
        method: "POST",
        body: JSON.stringify({ name, description: desc, github_urls: [url], repo_structure: "MONO" }),
      });
      // Start polling
      setProject(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  if (project) return <ProjectCloneStatus projectId={project.project_id} nav={nav} />;

  return (
    <div className="max-w-2xl mx-auto px-6 py-10">
      <button onClick={() => nav("dashboard")} className="text-gray-500 hover:text-gray-300 text-sm mb-6">← Back</button>
      <h2 className="text-2xl font-bold mb-6">New Project</h2>
      <form onSubmit={handleSubmit} className="space-y-4">
        <Field label="Project Name">
          <input value={name} onChange={e => setName(e.target.value)} required
            className="w-full bg-gray-800 rounded-lg px-4 py-2 text-white border border-gray-700 focus:outline-none focus:border-cyan-500" />
        </Field>
        <Field label="Description">
          <input value={desc} onChange={e => setDesc(e.target.value)}
            className="w-full bg-gray-800 rounded-lg px-4 py-2 text-white border border-gray-700 focus:outline-none focus:border-cyan-500" />
        </Field>
        <Field label="GitHub Repository URL">
          <input value={url} onChange={e => setUrl(e.target.value)} required
            placeholder="https://github.com/org/repo"
            className="w-full bg-gray-800 rounded-lg px-4 py-2 text-white border border-gray-700 focus:outline-none focus:border-cyan-500" />
        </Field>
        {error && <p className="text-red-400 text-sm">{error}</p>}
        <button type="submit" disabled={loading}
          className="w-full bg-cyan-600 hover:bg-cyan-500 disabled:opacity-50 text-white font-semibold py-3 rounded-xl">
          {loading ? "Creating..." : "Create Project"}
        </button>
      </form>
    </div>
  );
}

function ProjectCloneStatus({ projectId, nav }) {
  const [project, setProject] = useState(null);

  useEffect(() => {
    const poll = setInterval(async () => {
      try {
        const data = await apiFetch(`/projects/${projectId}`);
        setProject(data);
        const allDone = data.repos.every(r => r.clone_status === "DONE" || r.clone_status === "FAILED");
        if (allDone) clearInterval(poll);
      } catch (e) { clearInterval(poll); }
    }, 2000);
    return () => clearInterval(poll);
  }, [projectId]);

  if (!project) return <div className="max-w-2xl mx-auto px-6 py-10"><Spinner /></div>;

  const allDone = project.repos.every(r => r.clone_status === "DONE" || r.clone_status === "FAILED");
  const hasCompose = project.generated_compose;

  return (
    <div className="max-w-2xl mx-auto px-6 py-10">
      <h2 className="text-2xl font-bold mb-6">{project.name}</h2>
      {project.repos.map(r => (
        <div key={r.id} className="bg-gray-900 rounded-xl p-4 mb-4">
          <div className="flex items-center justify-between">
            <span className="font-medium">{r.repo_name}</span>
            <CloneStatusBadge status={r.clone_status} />
          </div>
        </div>
      ))}
      {allDone && !hasCompose && (
        <p className="text-cyan-400 text-sm animate-pulse mt-2">🤖 AI analyzing codebase and writing sandbox config...</p>
      )}
      {allDone && hasCompose && (
        <div className="mt-4">
          <p className="text-green-400 text-sm mb-4">✅ Ready — AI has written sandbox config</p>
          {project.detected_stack && (
            <div className="flex gap-2 flex-wrap mb-4">
              {(project.detected_stack.databases || []).map(d => <Badge key={d} label={d} icon="🗄" color="blue" />)}
              {(project.detected_stack.queues || []).map(q => <Badge key={q} label={q} icon="📨" color="purple" />)}
            </div>
          )}
          <button onClick={() => nav("project", project)}
            className="bg-cyan-600 hover:bg-cyan-500 text-white font-semibold px-6 py-3 rounded-xl">
            View Project →
          </button>
        </div>
      )}
    </div>
  );
}

// ── Screen 3: Project Feature List ────────────────────────────────────────────

function ProjectView({ project: initialProject, nav }) {
  const [project, setProject] = useState(initialProject);

  useEffect(() => {
    apiFetch(`/projects/${initialProject.id}`).then(setProject).catch(console.error);
  }, [initialProject.id]);

  return (
    <div className="max-w-5xl mx-auto px-6 py-10">
      <button onClick={() => nav("dashboard")} className="text-gray-500 hover:text-gray-300 text-sm mb-6">← Dashboard</button>
      <div className="flex items-center justify-between mb-8">
        <div>
          <h2 className="text-2xl font-bold">{project.name}</h2>
          <p className="text-gray-400 text-sm">{project.description}</p>
        </div>
        <button onClick={() => nav("add-feature", project)}
          className="bg-cyan-600 hover:bg-cyan-500 text-white px-4 py-2 rounded-lg text-sm font-medium">
          + Add Feature
        </button>
      </div>

      {project.features?.length === 0 ? (
        <div className="text-center text-gray-500 py-20">
          <p>No features yet.</p>
          <button onClick={() => nav("add-feature", project)} className="mt-4 text-cyan-400 hover:underline">Add your first feature</button>
        </div>
      ) : (
        <div className="space-y-3">
          {(project.features || []).map(f => (
            <FeatureRow key={f.id} feature={f} projectId={project.id} nav={nav} />
          ))}
        </div>
      )}
    </div>
  );
}

function FeatureRow({ feature, projectId, nav }) {
  async function handleView() {
    const full = await apiFetch(`/features/${feature.id}`);
    if (full.status === "AWAITING_METRIC_APPROVAL") {
      nav("metric-approval", null, full);
    } else if (full.status === "RUNNING" || full.status === "DONE" || full.status === "PARTIAL") {
      nav("live-loop", null, full);
    }
  }

  return (
    <div className="bg-gray-900 rounded-xl p-5 flex items-center justify-between">
      <div>
        <span className="font-medium">{feature.title}</span>
        {feature.feature_branch && (
          <span className="ml-3 text-xs text-gray-500 font-mono">{feature.feature_branch}</span>
        )}
      </div>
      <div className="flex items-center gap-4">
        <FeatureStatusBadge status={feature.status} />
        <button onClick={handleView} className="text-sm text-cyan-400 hover:underline">View →</button>
      </div>
    </div>
  );
}

// ── Screen 4: Add Feature ─────────────────────────────────────────────────────

function AddFeature({ project, nav }) {
  const [title, setTitle] = useState("");
  const [req, setReq] = useState("");
  const [featureId, setFeatureId] = useState(null);
  const [status, setStatus] = useState(null);
  const [clarifyQuestions, setClarifyQuestions] = useState([]);
  const [clarifyAnswers, setClarifyAnswers] = useState({});

  async function handleSubmit(e) {
    e.preventDefault();
    const data = await apiFetch(`/projects/${project.id}/features`, {
      method: "POST",
      body: JSON.stringify({ title, raw_requirement: req }),
    });
    setFeatureId(data.feature_id);
    setStatus("INTERCEPTING");
  }

  useEffect(() => {
    if (!featureId) return;
    const poll = setInterval(async () => {
      const f = await apiFetch(`/features/${featureId}`);
      setStatus(f.status);
      if (f.status === "AWAITING_CLARIFICATION" && f.module_spec?.clarifying_questions?.length) {
        setClarifyQuestions(f.module_spec.clarifying_questions);
        clearInterval(poll);
      } else if (f.status === "AWAITING_METRIC_APPROVAL") {
        clearInterval(poll);
        // Generate metric plan then navigate
        await apiFetch("/requirements/metric-plan", {
          method: "POST",
          body: JSON.stringify({ feature_id: featureId }),
        });
        const updated = await apiFetch(`/features/${featureId}`);
        nav("metric-approval", null, updated);
      } else if (f.status === "CANCELLED") {
        clearInterval(poll);
      }
    }, 2000);
    return () => clearInterval(poll);
  }, [featureId]);

  async function handleClarify(e) {
    e.preventDefault();
    await apiFetch(`/features/${featureId}/clarify`, {
      method: "POST",
      body: JSON.stringify({ answers: clarifyAnswers }),
    });
    setClarifyQuestions([]);
    setStatus("INTERCEPTING");
  }

  if (!featureId) return (
    <div className="max-w-2xl mx-auto px-6 py-10">
      <button onClick={() => nav("project", project)} className="text-gray-500 hover:text-gray-300 text-sm mb-6">← Back</button>
      <h2 className="text-2xl font-bold mb-6">Add Feature</h2>
      <form onSubmit={handleSubmit} className="space-y-4">
        <Field label="Feature Title">
          <input value={title} onChange={e => setTitle(e.target.value)} required
            className="w-full bg-gray-800 rounded-lg px-4 py-2 text-white border border-gray-700 focus:outline-none focus:border-cyan-500" />
        </Field>
        <Field label="Requirement">
          <textarea value={req} onChange={e => setReq(e.target.value)} required rows={5}
            placeholder="Describe what you want to build..."
            className="w-full bg-gray-800 rounded-lg px-4 py-2 text-white border border-gray-700 focus:outline-none focus:border-cyan-500" />
        </Field>
        <button type="submit" className="w-full bg-cyan-600 hover:bg-cyan-500 text-white font-semibold py-3 rounded-xl">
          Analyze Requirement
        </button>
      </form>
    </div>
  );

  if (clarifyQuestions.length > 0) return (
    <div className="max-w-2xl mx-auto px-6 py-10">
      <h2 className="text-2xl font-bold mb-2">Clarification Needed</h2>
      <p className="text-gray-400 mb-6">Please answer these questions to proceed:</p>
      <form onSubmit={handleClarify} className="space-y-4">
        {clarifyQuestions.map((q, i) => (
          <Field key={i} label={q}>
            <input value={clarifyAnswers[q] || ""} onChange={e => setClarifyAnswers(a => ({ ...a, [q]: e.target.value }))}
              className="w-full bg-gray-800 rounded-lg px-4 py-2 text-white border border-gray-700 focus:outline-none focus:border-cyan-500" />
          </Field>
        ))}
        <button type="submit" className="w-full bg-cyan-600 hover:bg-cyan-500 text-white font-semibold py-3 rounded-xl">
          Continue
        </button>
      </form>
    </div>
  );

  return (
    <div className="max-w-2xl mx-auto px-6 py-10 text-center">
      <Spinner />
      <p className="mt-4 text-cyan-400 animate-pulse">🤖 Analyzing requirement...</p>
      <p className="text-xs text-gray-500 mt-2">Status: {status}</p>
    </div>
  );
}

// ── Screen 5: Metric Approval ─────────────────────────────────────────────────

function MetricApproval({ feature, nav }) {
  const [loading, setLoading] = useState(false);
  const plan = feature.benchmark_plan;

  async function handleApprove() {
    setLoading(true);
    try {
      const data = await apiFetch("/requirements/approve-metric", {
        method: "POST",
        body: JSON.stringify({ feature_id: feature.id, approved: true }),
      });
      const updated = { ...feature, status: "RUNNING", session_id: data.session_id, feature_branch: data.feature_branch };
      nav("live-loop", null, updated);
    } finally {
      setLoading(false);
    }
  }

  if (!plan) return <div className="max-w-2xl mx-auto px-6 py-10"><Spinner /></div>;

  const categories = plan.planned_test_cases || {};
  const categoryIcons = { happy_path: "✅", security: "🔒", boundary: "📏", null_input: "⚠️", edge_case: "🔀" };

  return (
    <div className="max-w-2xl mx-auto px-6 py-10">
      <div className="bg-gray-900 rounded-2xl p-8 border border-gray-800">
        <h2 className="text-xl font-bold mb-1">📊 Here's exactly what we will measure</h2>
        <p className="text-gray-400 text-sm mb-6">Review and approve before development begins</p>

        <div className="space-y-3 mb-6">
          <Row label="Metric" value={plan.metric} />
          <Row label="Formula" value={plan.formula} />
          <Row label="Target" value={plan.target} />
          <Row label="Total Tests" value={`${plan.total_planned} test cases`} />
        </div>

        <div className="mb-6">
          <p className="text-sm font-semibold text-gray-300 mb-2">Test breakdown:</p>
          <div className="space-y-1">
            {Object.entries(categories).map(([cat, info]) => (
              <div key={cat} className="flex items-center gap-3 text-sm">
                <span>{categoryIcons[cat] || "•"}</span>
                <span className="text-gray-400 w-24">{cat.replace("_", " ")}</span>
                <span className="text-white font-medium">{info.count}</span>
                <span className="text-gray-500 text-xs">{(info.examples || []).slice(0, 2).join(", ")}</span>
              </div>
            ))}
          </div>
        </div>

        {plan.real_infra_testing && (
          <div className="bg-blue-900/30 rounded-xl p-4 mb-6 text-sm">
            <p className="text-blue-300 font-medium mb-1">🐳 Real infrastructure testing</p>
            <p className="text-blue-400">{plan.infra_services?.join(" · ")}</p>
            <p className="text-gray-400 text-xs mt-1">{plan.infra_note}</p>
          </div>
        )}

        <div className="text-sm text-gray-400 mb-6">
          <p>⏱ ~{plan.estimated_seconds_per_iteration}s per iteration</p>
          <p>📁 Code pushed to: <code className="text-cyan-400">feature/{"{session_id}"}</code></p>
        </div>

        <div className="flex gap-3">
          <button onClick={handleApprove} disabled={loading}
            className="flex-1 bg-green-600 hover:bg-green-500 disabled:opacity-50 text-white font-semibold py-3 rounded-xl">
            {loading ? "Starting..." : "✅ Approve & Start Development"}
          </button>
          <button onClick={() => nav("project", null)}
            className="px-6 bg-gray-800 hover:bg-gray-700 text-white rounded-xl">
            ✏️ Edit
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Screen 6: Live Loop Dashboard ─────────────────────────────────────────────

function LiveLoop({ feature, nav }) {
  const [iterations, setIterations] = useState([]);
  const [currentFeature, setCurrentFeature] = useState(feature);
  const [expanded, setExpanded] = useState(null);

  useEffect(() => {
    if (!feature.session_id) return;
    const poll = setInterval(async () => {
      try {
        const f = await apiFetch(`/features/${feature.id}`);
        setCurrentFeature(f);
        if (f.status === "DONE" || f.status === "PARTIAL") {
          clearInterval(poll);
        }
      } catch (e) {}
    }, 3000);
    return () => clearInterval(poll);
  }, [feature.id]);

  const isDone = currentFeature.status === "DONE" || currentFeature.status === "PARTIAL";
  const bestScore = iterations.length > 0 ? Math.max(...iterations.map(i => i.score)) : null;

  return (
    <div className="max-w-4xl mx-auto px-6 py-10">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h2 className="text-xl font-bold">Building: {currentFeature.title}</h2>
          {currentFeature.feature_branch && (
            <p className="text-sm text-gray-500 font-mono mt-1">{currentFeature.feature_branch}</p>
          )}
        </div>
        <FeatureStatusBadge status={currentFeature.status} large />
      </div>

      {!isDone && (
        <div className="text-center py-10">
          <Spinner />
          <p className="mt-4 text-cyan-400 animate-pulse">🤖 Running autonomous development loop...</p>
        </div>
      )}

      {isDone && (
        <div className={`rounded-2xl p-6 mb-6 ${currentFeature.status === "DONE" ? "bg-green-900/30 border border-green-800" : "bg-amber-900/30 border border-amber-800"}`}>
          {currentFeature.status === "DONE" ? (
            <p className="text-green-300 text-lg font-semibold">✅ Task completed successfully!</p>
          ) : (
            <p className="text-amber-300 text-lg font-semibold">⚠️ Best effort result</p>
          )}
          {currentFeature.feature_branch && (
            <p className="text-sm text-gray-400 mt-2">
              🚀 Pushed to: <code className="text-cyan-400">{currentFeature.feature_branch}</code>
            </p>
          )}
        </div>
      )}
    </div>
  );
}

// ── Shared components ─────────────────────────────────────────────────────────

function Spinner() {
  return (
    <div className="flex justify-center">
      <div className="w-8 h-8 border-2 border-cyan-400 border-t-transparent rounded-full animate-spin" />
    </div>
  );
}

function Badge({ label, icon, color }) {
  const colors = { blue: "bg-blue-900/50 text-blue-300", purple: "bg-purple-900/50 text-purple-300", green: "bg-green-900/50 text-green-300" };
  return (
    <span className={`text-xs px-2 py-1 rounded-md ${colors[color] || "bg-gray-800 text-gray-300"}`}>
      {icon} {label}
    </span>
  );
}

function CloneStatusBadge({ status }) {
  const map = {
    PENDING: ["bg-gray-700", "Pending"],
    CLONING: ["bg-yellow-700 animate-pulse", "Cloning..."],
    DONE: ["bg-green-700", "✅ Done"],
    FAILED: ["bg-red-700", "❌ Failed"],
  };
  const [cls, label] = map[status] || ["bg-gray-700", status];
  return <span className={`text-xs px-3 py-1 rounded-full text-white ${cls}`}>{label}</span>;
}

function FeatureStatusBadge({ status, large }) {
  const map = {
    INTERCEPTING: ["bg-yellow-900/50 text-yellow-300", "Analyzing"],
    AWAITING_CLARIFICATION: ["bg-orange-900/50 text-orange-300", "Needs Input"],
    AWAITING_METRIC_APPROVAL: ["bg-blue-900/50 text-blue-300", "Awaiting Approval"],
    RUNNING: ["bg-cyan-900/50 text-cyan-300 animate-pulse", "Running"],
    DONE: ["bg-green-900/50 text-green-300", "✅ Done"],
    PARTIAL: ["bg-amber-900/50 text-amber-300", "⚠️ Partial"],
    CANCELLED: ["bg-red-900/50 text-red-300", "Cancelled"],
  };
  const [cls, label] = map[status] || ["bg-gray-800 text-gray-400", status];
  return <span className={`px-3 py-1 rounded-full text-xs font-medium ${cls} ${large ? "text-sm" : ""}`}>{label}</span>;
}

function Field({ label, children }) {
  return (
    <div>
      <label className="block text-sm text-gray-400 mb-1">{label}</label>
      {children}
    </div>
  );
}

function Row({ label, value }) {
  return (
    <div className="flex items-center gap-4">
      <span className="text-sm text-gray-400 w-28">{label}:</span>
      <span className="text-sm text-white">{value}</span>
    </div>
  );
}

function GitHubIcon() {
  return (
    <svg height="20" viewBox="0 0 16 16" fill="currentColor">
      <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z" />
    </svg>
  );
}
