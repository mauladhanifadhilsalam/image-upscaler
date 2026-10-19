import { useEffect, useState } from "react";
import { createJob, getJob, getLimits, type Job, type Limits, type Scale } from "./api";
import Dropzone from "./components/Dropzone";
import DownloadAllButton from "./components/DownloadAllButton";
import FileQueue from "./components/FileQueue";
import ScaleSelector from "./components/ScaleSelector";

const DEFAULT_LIMITS: Limits = {
  scales: [2, 4],
  max_file_bytes: 10 * 1024 * 1024,
  max_files: 20,
  max_input_side: { "2": 4096, "4": 2048 },
  formats: ["image/jpeg", "image/png", "image/webp"],
};

interface Pending {
  file: File;
  preview: string;
  width: number;
  height: number;
}

function readSize(file: File, preview: string): Promise<Pending> {
  return new Promise((resolve) => {
    const img = new Image();
    img.onload = () => resolve({ file, preview, width: img.naturalWidth, height: img.naturalHeight });
    img.onerror = () => resolve({ file, preview, width: 0, height: 0 });
    img.src = preview;
  });
}

export default function App() {
  const [limits, setLimits] = useState(DEFAULT_LIMITS);
  const [scale, setScale] = useState<Scale>(2);
  const [pending, setPending] = useState<Pending[]>([]);
  const [job, setJob] = useState<Job | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getLimits().then(setLimits).catch(() => {});
  }, []);

  // Poll the job until every file has finished.
  useEffect(() => {
    if (!job || job.status === "done") return;
    const timer = setTimeout(() => {
      getJob(job.id).then(setJob).catch((e: Error) => setError(e.message));
    }, 1000);
    return () => clearTimeout(timer);
  }, [job]);

  const maxSide = limits.max_input_side[String(scale)];
  const tooLarge = (p: Pending) => Math.max(p.width, p.height) > maxSide;
  const ready = pending.filter((p) => !tooLarge(p));

  async function addFiles(files: File[]) {
    setError(null);
    const room = limits.max_files - pending.length;
    if (files.length > room) setError(`A batch can hold at most ${limits.max_files} images.`);
    const added = await Promise.all(files.slice(0, Math.max(room, 0)).map((f) => readSize(f, URL.createObjectURL(f))));
    setPending((prev) => [...prev, ...added]);
  }

  function removeFile(index: number) {
    setPending((prev) => {
      URL.revokeObjectURL(prev[index].preview);
      return prev.filter((_, i) => i !== index);
    });
  }

  async function start() {
    setSubmitting(true);
    setError(null);
    try {
      setJob(await createJob(ready.map((p) => p.file), scale));
      pending.forEach((p) => URL.revokeObjectURL(p.preview));
      setPending([]);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSubmitting(false);
    }
  }

  function reset() {
    setJob(null);
    setError(null);
  }

  return (
    <div className="min-h-screen bg-gradient-to-b from-indigo-50 to-slate-50 text-slate-900">
      <main className="mx-auto max-w-3xl px-4 py-12">
        <header className="mb-8 text-center">
          <h1 className="text-3xl font-bold tracking-tight sm:text-4xl">AI Image Upscaler</h1>
          <p className="mt-2 text-slate-600">
            Enlarge photos to 200% or 400% with Real-ESRGAN, one image or a whole batch at a time.
          </p>
        </header>

        {error && (
          <div role="alert" className="mb-4 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
            {error}
          </div>
        )}

        {job ? (
          <section className="space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h2 className="text-lg font-semibold">
                  Upscaling {job.files.length} image{job.files.length > 1 ? "s" : ""} to {job.scale * 100}%
                </h2>
                <p className="text-sm text-slate-500" data-testid="job-progress">
                  {job.status === "done" ? "All done" : `${Math.round(job.progress * 100)}% complete`}
                </p>
              </div>
              <div className="flex gap-2">
                <DownloadAllButton job={job} />
                <button
                  type="button"
                  onClick={reset}
                  className="rounded-xl border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50"
                >
                  Upscale more
                </button>
              </div>
            </div>
            <FileQueue job={job} />
          </section>
        ) : (
          <section className="space-y-5 rounded-3xl bg-white/70 p-5 shadow-sm ring-1 ring-slate-200 sm:p-8">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <span className="text-sm font-semibold text-slate-700">Upscale factor</span>
              <ScaleSelector value={scale} onChange={setScale} disabled={submitting} />
            </div>

            <Dropzone onFiles={addFiles} onReject={setError} maxSize={limits.max_file_bytes} disabled={submitting} />

            {pending.length > 0 && (
              <>
                <ul className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                  {pending.map((p, i) => (
                    <li key={p.preview} className="group relative overflow-hidden rounded-xl bg-slate-100" data-testid="pending-file">
                      <img src={p.preview} alt={p.file.name} className="h-28 w-full object-cover" />
                      <div className="absolute inset-x-0 bottom-0 bg-black/60 px-2 py-1 text-xs text-white">
                        <p className="truncate">{p.file.name}</p>
                        <p className={tooLarge(p) ? "text-rose-300" : "text-white/70"}>
                          {tooLarge(p) ? `Too large for ${scale}x (max ${maxSide}px)` : `${p.width}×${p.height} → ${p.width * scale}×${p.height * scale}`}
                        </p>
                      </div>
                      <button
                        type="button"
                        onClick={() => removeFile(i)}
                        aria-label={`Remove ${p.file.name}`}
                        className="absolute top-1 right-1 flex h-6 w-6 items-center justify-center rounded-full bg-black/60 text-sm text-white hover:bg-black/80"
                      >
                        ×
                      </button>
                    </li>
                  ))}
                </ul>
                <button
                  type="button"
                  onClick={start}
                  disabled={submitting || ready.length === 0}
                  className="w-full rounded-xl bg-indigo-600 py-3 text-base font-semibold text-white shadow hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {submitting ? "Uploading…" : `Upscale ${ready.length} image${ready.length === 1 ? "" : "s"} to ${scale * 100}%`}
                </button>
              </>
            )}
          </section>
        )}
      </main>
    </div>
  );
}
