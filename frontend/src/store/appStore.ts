import { create } from "zustand";

import { apiClient } from "../api/apiClient";
import type {
  FeatureDetail,
  ProjectDetail,
  ProjectSummary,
  UserProfile,
} from "../types/models";

type Screen =
  | "dashboard"
  | "new-project"
  | "project"
  | "add-feature"
  | "metric-approval"
  | "live-loop";

interface AppState {
  token: string | null;
  me: UserProfile | null;
  projects: ProjectSummary[];
  selectedProject: ProjectDetail | null;
  selectedFeature: FeatureDetail | null;
  loading: boolean;
  error: string | null;
  screen: Screen;

  setScreen: (screen: Screen) => void;
  setError: (error: string | null) => void;
  clearError: () => void;

  hydrateTokenFromUrl: () => boolean;
  logout: () => void;

  fetchMe: () => Promise<void>;
  fetchProjects: () => Promise<void>;
  fetchProjectDetail: (projectId: string) => Promise<ProjectDetail>;
  fetchFeatureDetail: (featureId: string) => Promise<FeatureDetail>;

  createProject: (payload: {
    name: string;
    description: string;
    github_urls: string[];
    repo_structure: "MONO";
  }) => Promise<{ project_id: string }>;

  createFeature: (
    projectId: string,
    payload: { title: string; raw_requirement: string },
  ) => Promise<{ feature_id: string }>;

  clarifyFeature: (
    featureId: string,
    answers: Record<string, string>,
  ) => Promise<void>;
  generateMetricPlan: (featureId: string) => Promise<void>;
  approveMetric: (
    featureId: string,
  ) => Promise<{ session_id: string; feature_branch?: string }>;
}

function setToken(token: string | null): void {
  if (token) {
    localStorage.setItem("gbads_token", token);
  } else {
    localStorage.removeItem("gbads_token");
  }
}

export const useAppStore = create<AppState>((set, get) => ({
  token: localStorage.getItem("gbads_token"),
  me: null,
  projects: [],
  selectedProject: null,
  selectedFeature: null,
  loading: false,
  error: null,
  screen: "dashboard",

  setScreen: (screen) => set({ screen }),
  setError: (error) => set({ error }),
  clearError: () => set({ error: null }),

  hydrateTokenFromUrl: () => {
    const rawSearch =
      window.location.search ||
      (window.location.hash.startsWith("#")
        ? window.location.hash.slice(1)
        : "");
    const params = new URLSearchParams(rawSearch);
    const token = params.get("token");
    if (token) {
      setToken(token);
      set({ token, error: null });
      window.history.replaceState({}, "", window.location.pathname);
      return true;
    }
    return false;
  },

  logout: () => {
    setToken(null);
    set({
      token: null,
      me: null,
      projects: [],
      selectedProject: null,
      selectedFeature: null,
      screen: "dashboard",
      error: null,
    });
  },

  fetchMe: async () => {
    const me = await apiClient.get<UserProfile>("/auth/me");
    set({ me });
  },

  fetchProjects: async () => {
    set({ loading: true, error: null });
    try {
      const projects = await apiClient.get<ProjectSummary[]>("/projects");
      set({ projects });
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Failed to load projects";
      set({ error: message });
      throw err;
    } finally {
      set({ loading: false });
    }
  },

  fetchProjectDetail: async (projectId: string) => {
    const project = await apiClient.get<ProjectDetail>(
      `/projects/${projectId}`,
    );
    set({ selectedProject: project });
    return project;
  },

  fetchFeatureDetail: async (featureId: string) => {
    const feature = await apiClient.get<FeatureDetail>(
      `/features/${featureId}`,
    );
    set({ selectedFeature: feature });
    return feature;
  },

  createProject: async (payload) => {
    const data = await apiClient.post<{ project_id: string }>(
      "/projects",
      payload,
    );
    await get().fetchProjects();
    return data;
  },

  createFeature: async (projectId, payload) => {
    return apiClient.post<{ feature_id: string }>(
      `/projects/${projectId}/features`,
      payload,
    );
  },

  clarifyFeature: async (featureId, answers) => {
    await apiClient.post(`/features/${featureId}/clarify`, { answers });
  },

  generateMetricPlan: async (featureId) => {
    await apiClient.post("/requirements/metric-plan", {
      feature_id: featureId,
    });
  },

  approveMetric: async (featureId) => {
    return apiClient.post<{ session_id: string; feature_branch?: string }>(
      "/requirements/approve-metric",
      {
        feature_id: featureId,
        approved: true,
      },
    );
  },
}));

export function getGithubLoginUrl(): string {
  const base = apiClient.getBaseUrl();
  return `${base}/auth/github`;
}
