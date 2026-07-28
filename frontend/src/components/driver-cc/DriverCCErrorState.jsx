import React from "react";

export default function DriverCCErrorState({ onRetry }) {
  return (
    <div className="mb-4 p-3 rounded-lg bg-red-50 border border-red-200 text-sm text-red-800 flex items-center justify-between" data-testid="profile-load-error">
      <span>Could not load some of the Driver Profile. Try again.</span>
      <button onClick={onRetry} className="text-red-900 underline text-xs" data-testid="profile-load-retry">Retry</button>
    </div>
  );
}
