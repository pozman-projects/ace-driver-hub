import React from "react";

export function SkeletonRow() {
  return (
    <div className="space-y-6">
      {[1, 2, 3].map((r) => (
        <div key={r} className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {[1, 2, 3].map((c) => (
            <div key={c} className="h-52 bg-white rounded-xl border border-slate-200 animate-pulse" />
          ))}
        </div>
      ))}
    </div>
  );
}

export function SkeletonRight() {
  return (
    <>
      {[1, 2, 3, 4, 5, 6].map((i) => (
        <div key={i} className="h-32 bg-white rounded-xl border border-slate-200 animate-pulse" />
      ))}
    </>
  );
}
