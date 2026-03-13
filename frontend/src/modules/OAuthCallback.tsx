import { useEffect } from "react";

import { Spinner } from "../components/Shared";
import { useAppStore } from "../store/appStore";

export default function OAuthCallback(): JSX.Element {
  const hydrateTokenFromUrl = useAppStore((s) => s.hydrateTokenFromUrl);

  useEffect(() => {
    hydrateTokenFromUrl();
    // Use hard redirect to avoid any router-state edge case after third-party OAuth redirects.
    window.location.replace("/");
  }, [hydrateTokenFromUrl]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-950 text-gray-100">
      <div className="text-center">
        <Spinner />
        <p className="text-sm text-gray-400 mt-4">Completing GitHub login...</p>
      </div>
    </div>
  );
}
