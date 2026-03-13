import { getGithubLoginUrl } from "../store/appStore";
import { GitHubIcon } from "../components/Shared";

export default function LoginScreen(): JSX.Element {
  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-950">
      <div className="bg-gray-900 p-10 rounded-2xl shadow-xl text-center max-w-md w-full">
        <h1 className="text-3xl font-bold text-cyan-400 mb-2">GBADS</h1>
        <p className="text-gray-400 mb-8">
          Goal-Based Autonomous Development System
        </p>
        <a
          href={getGithubLoginUrl()}
          className="inline-flex items-center gap-3 bg-gray-800 hover:bg-gray-700 text-white font-semibold px-6 py-3 rounded-xl transition"
        >
          <GitHubIcon />
          Login with GitHub
        </a>
        <p className="text-xs text-gray-600 mt-4">
          Requires repo scope to clone private repos
        </p>
      </div>
    </div>
  );
}
