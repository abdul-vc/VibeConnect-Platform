import { useState, type FC } from "react";
import { apiClient } from "../api/client.ts";
import type { HealthCheckResponse } from "../api/types.ts";
import { LoadingSpinner } from "../components/LoadingSpinner.tsx";

export const FoundationPage: FC = () => {
  const [healthStatus, setHealthStatus] = useState<HealthCheckResponse | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const handleHealthCheck = async () => {
    setIsLoading(true);
    setErrorMessage(null);
    try {
      const response = await apiClient.checkHealth();
      setHealthStatus(response);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Failed to connect to backend.";
      setErrorMessage(message);
      setHealthStatus(null);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col items-center justify-center p-6 antialiased">
      <div className="max-w-xl w-full bg-slate-900 border border-slate-800 rounded-2xl p-8 shadow-2xl space-y-6">
        <div className="space-y-2 text-center">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-indigo-500/10 border border-indigo-500/20 text-indigo-400 text-xs font-semibold uppercase tracking-wider">
            Control Plane
          </div>
          <h1 className="text-3xl font-bold tracking-tight text-white">Envisage</h1>
          <p className="text-sm text-slate-400">
            Enterprise Multi-Tenant SaaS Master Platform Foundation
          </p>
        </div>

        <div className="bg-slate-950/60 border border-slate-800/80 rounded-xl p-5 space-y-4">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-slate-400 uppercase tracking-wider">
              Control Plane Status
            </span>
            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
              Foundation Initialized
            </span>
          </div>

          <div className="border-t border-slate-800/60 pt-4 flex flex-col gap-3">
            <div className="flex items-center justify-between text-xs">
              <span className="text-slate-500">Backend API Integration</span>
              <button
                id="btn-check-health"
                onClick={handleHealthCheck}
                disabled={isLoading}
                className="px-3 py-1.5 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white text-xs font-semibold rounded-md shadow transition-colors"
              >
                {isLoading ? "Checking..." : "Verify Backend Health"}
              </button>
            </div>

            {isLoading && <LoadingSpinner label="Testing backend connection..." />}

            {healthStatus && (
              <div className="mt-2 p-3 bg-emerald-950/30 border border-emerald-800/40 rounded-lg text-xs space-y-1">
                <div className="flex justify-between">
                  <span className="text-emerald-400 font-semibold">Status:</span>
                  <span className="text-emerald-300">{healthStatus.status}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-emerald-400 font-semibold">Service:</span>
                  <span className="text-emerald-300">{healthStatus.service}</span>
                </div>
              </div>
            )}

            {errorMessage && (
              <div className="mt-2 p-3 bg-red-950/30 border border-red-800/40 rounded-lg text-xs space-y-1 text-red-300">
                <p className="font-semibold text-red-400">Connection Result:</p>
                <p>{errorMessage}</p>
              </div>
            )}
          </div>
        </div>

        <div className="text-center text-xs text-slate-500">
          Phase 1A Stage 1 — Project Foundation & PostgreSQL Configuration
        </div>
      </div>
    </div>
  );
};
