import { zipUrl, type Job } from "../api";

export default function DownloadAllButton({ job }: { job: Job }) {
  const done = job.files.filter((f) => f.status === "done").length;
  const ready = job.status === "done" && done > 0;

  return (
    <a
      href={ready ? zipUrl(job.id) : undefined}
      aria-disabled={!ready}
      className={`inline-flex items-center rounded-xl px-4 py-2 text-sm font-semibold ${
        ready ? "bg-emerald-600 text-white hover:bg-emerald-700" : "pointer-events-none bg-slate-200 text-slate-400"
      }`}
    >
      Download all ({done}) as ZIP
    </a>
  );
}
