import type { ReactNode } from "react";

import type { CloneStatus, FeatureStatus } from "../types/models";

export function Spinner(): JSX.Element {
  return (
    <div className="flex justify-center">
      <div className="w-8 h-8 border-2 border-cyan-400 border-t-transparent rounded-full animate-spin" />
    </div>
  );
}

export function Badge({
  label,
  icon,
  color,
}: {
  label: string;
  icon: string;
  color?: string;
}): JSX.Element {
  const colors: Record<string, string> = {
    blue: "bg-blue-900/50 text-blue-300",
    purple: "bg-purple-900/50 text-purple-300",
    green: "bg-green-900/50 text-green-300",
  };
  return (
    <span
      className={`text-xs px-2 py-1 rounded-md ${colors[color || ""] || "bg-gray-800 text-gray-300"}`}
    >
      {icon} {label}
    </span>
  );
}

export function CloneStatusBadge({
  status,
}: {
  status: CloneStatus;
}): JSX.Element {
  const map: Record<string, [string, string]> = {
    PENDING: ["bg-gray-700", "Pending"],
    CLONING: ["bg-yellow-700 animate-pulse", "Cloning..."],
    DONE: ["bg-green-700", "Done"],
    FAILED: ["bg-red-700", "Failed"],
  };
  const [cls, label] = map[status] || ["bg-gray-700", status];
  return (
    <span className={`text-xs px-3 py-1 rounded-full text-white ${cls}`}>
      {label}
    </span>
  );
}

export function FeatureStatusBadge({
  status,
  large,
}: {
  status: FeatureStatus;
  large?: boolean;
}): JSX.Element {
  const map: Record<string, [string, string]> = {
    INTERCEPTING: ["bg-yellow-900/50 text-yellow-300", "Analyzing"],
    AWAITING_CLARIFICATION: ["bg-orange-900/50 text-orange-300", "Needs Input"],
    AWAITING_METRIC_APPROVAL: [
      "bg-blue-900/50 text-blue-300",
      "Awaiting Approval",
    ],
    RUNNING: ["bg-cyan-900/50 text-cyan-300 animate-pulse", "Running"],
    DONE: ["bg-green-900/50 text-green-300", "Done"],
    PARTIAL: ["bg-amber-900/50 text-amber-300", "Partial"],
    CANCELLED: ["bg-red-900/50 text-red-300", "Cancelled"],
  };
  const [cls, label] = map[status] || ["bg-gray-800 text-gray-400", status];
  return (
    <span
      className={`px-3 py-1 rounded-full text-xs font-medium ${cls} ${large ? "text-sm" : ""}`}
    >
      {label}
    </span>
  );
}

export function Field({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}): JSX.Element {
  return (
    <div>
      <label className="block text-sm text-gray-400 mb-1">{label}</label>
      {children}
    </div>
  );
}

export function Row({
  label,
  value,
}: {
  label: string;
  value: string | number;
}): JSX.Element {
  return (
    <div className="flex items-center gap-4">
      <span className="text-sm text-gray-400 w-28">{label}:</span>
      <span className="text-sm text-white">{value}</span>
    </div>
  );
}

export function GitHubIcon(): JSX.Element {
  return (
    <svg height="20" viewBox="0 0 16 16" fill="currentColor">
      <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z" />
    </svg>
  );
}
