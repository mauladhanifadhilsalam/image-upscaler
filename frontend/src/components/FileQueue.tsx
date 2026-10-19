import { useState } from "react";
import { fileUrl, originalUrl, type Job, type JobFile } from "../api";
import BeforeAfterSlider from "./BeforeAfterSlider";

const STATUS_LABEL: Record<JobFile["status"], string> = {
  queued: "Waiting",
  processing: "Upscaling",
  done: "Done",
  error: "Failed",
};

const STATUS_STYLE: Record<JobFile["status"], string> = {
  queued: "bg-slate-100 text-slate-600",
  processing: "bg-amber-100 text-amber-700",
  done: "bg-emerald-100 text-emerald-700",
  error: "bg-rose-100 text-rose-700",
};

function FileRow({ jobId, file }: { jobId: string; file: JobFile }) {
  const [comparing, setComparing] = useState(false);
  const pct = Math.round((file.status === "done" ? 1 : file.progress) * 100);

  return (
    <li className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm" data-testid="job-file">
      <div className="flex flex-wrap items-center gap-4">
        <img src={originalUrl(jobId, file.id)} alt="" className="h-14 w-14 flex-none rounded-lg object-cover" />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <p className="truncate font-medium text-slate-800">{file.name}</p>
            <span className={`flex-none rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_STYLE[file.status]}`}>
              {STATUS_LABEL[file.status]}
            </span>
          </div>
          <p className="text-sm text-slate-500">
            {file.width}×{file.height} → {file.output_width}×{file.output_height}
          </p>
          {file.status === "error" ? (
            <p className="mt-1 text-sm text-rose-600">{file.error}</p>
          ) : file.status !== "done" ? (
            <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-slate-100">
              <div className="h-full rounded-full bg-indigo-500 transition-all" style={{ width: `${pct}%` }} />
            </div>
          ) : null}
        </div>
        {file.status === "done" && (
          <div className="flex w-full gap-2 sm:w-auto sm:flex-none">
            <button
              type="button"
              onClick={() => setComparing((c) => !c)}
              className="flex-1 rounded-lg border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
            >
              {comparing ? "Hide" : "Compare"}
            </button>
            <a
              href={fileUrl(jobId, file.id)}
              download={file.output_name ?? undefined}
              className="flex-1 rounded-lg bg-indigo-600 px-3 text-center py-1.5 text-sm font-medium text-white hover:bg-indigo-700"
            >
              Download
            </a>
          </div>
        )}
      </div>
      {comparing && (
        <div className="mt-4">
          <BeforeAfterSlider before={originalUrl(jobId, file.id)} after={fileUrl(jobId, file.id)} alt={file.name} />
        </div>
      )}
    </li>
  );
}

export default function FileQueue({ job }: { job: Job }) {
  return (
    <ul className="space-y-3">
      {job.files.map((f) => (
        <FileRow key={f.id} jobId={job.id} file={f} />
      ))}
    </ul>
  );
}
