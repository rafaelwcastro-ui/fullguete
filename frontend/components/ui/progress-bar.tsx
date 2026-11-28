// Adapted from Tremor Raw ProgressBar v0.0.3 (Apache-2.0).
// https://github.com/tremorlabs/tremor/blob/main/src/components/ProgressBar/ProgressBar.tsx
export function ProgressBar({ value, label }: { value: number; label: string }) {
  const percent = Math.min(100, Math.max(0, value));

  return (
    <div
      className="flex h-2 w-full items-center rounded-full bg-border"
      role="progressbar"
      aria-label={label}
      aria-valuenow={percent}
    >
      <div
        className="h-full rounded-full bg-gradient-to-r from-secondary to-primary"
        style={{ width: `${percent}%` }}
      />
    </div>
  );
}
