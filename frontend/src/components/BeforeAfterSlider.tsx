import { useState } from "react";

interface Props {
  before: string;
  after: string;
  alt: string;
}

export default function BeforeAfterSlider({ before, after, alt }: Props) {
  const [position, setPosition] = useState(50);

  return (
    <div className="relative select-none overflow-hidden rounded-xl bg-[repeating-conic-gradient(#e2e8f0_0%_25%,#fff_0%_50%)] bg-[length:16px_16px]" data-testid="compare">
      <img src={after} alt={`${alt} upscaled`} className="block h-auto w-full" draggable={false} />
      <img
        src={before}
        alt={`${alt} original`}
        className="absolute inset-0 h-full w-full"
        style={{ clipPath: `inset(0 ${100 - position}% 0 0)` }}
        draggable={false}
      />
      <div className="pointer-events-none absolute inset-y-0 w-0.5 bg-white shadow" style={{ left: `${position}%` }}>
        <div className="absolute top-1/2 left-1/2 flex h-8 w-8 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full bg-white text-xs font-bold text-slate-700 shadow">
          ⇆
        </div>
      </div>
      <span className="absolute top-2 left-2 rounded bg-black/60 px-2 py-0.5 text-xs text-white">Original</span>
      <span className="absolute top-2 right-2 rounded bg-indigo-600/90 px-2 py-0.5 text-xs text-white">Upscaled</span>
      <input
        type="range"
        min={0}
        max={100}
        value={position}
        onChange={(e) => setPosition(Number(e.target.value))}
        aria-label="Compare original and upscaled"
        className="absolute inset-0 h-full w-full cursor-ew-resize opacity-0"
      />
    </div>
  );
}
