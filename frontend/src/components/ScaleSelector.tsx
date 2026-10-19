import type { Scale } from "../api";

const OPTIONS: { scale: Scale; label: string; hint: string }[] = [
  { scale: 2, label: "200%", hint: "2x upscale" },
  { scale: 4, label: "400%", hint: "4x upscale" },
];

interface Props {
  value: Scale;
  onChange: (scale: Scale) => void;
  disabled?: boolean;
}

export default function ScaleSelector({ value, onChange, disabled }: Props) {
  return (
    <div role="radiogroup" aria-label="Upscale factor" className="inline-flex rounded-xl bg-slate-100 p-1">
      {OPTIONS.map((o) => (
        <button
          key={o.scale}
          type="button"
          role="radio"
          aria-checked={value === o.scale}
          disabled={disabled}
          onClick={() => onChange(o.scale)}
          className={`rounded-lg px-5 py-2 text-sm font-semibold transition disabled:cursor-not-allowed disabled:opacity-60 ${
            value === o.scale ? "bg-white text-indigo-600 shadow" : "text-slate-600 hover:text-slate-900"
          }`}
        >
          {o.label}
          <span className="ml-1 hidden font-normal text-slate-400 sm:inline">({o.hint})</span>
        </button>
      ))}
    </div>
  );
}
