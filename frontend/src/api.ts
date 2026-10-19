const BASE = import.meta.env.VITE_API_URL ?? "";

export type Scale = 2 | 4;
export type FileStatus = "queued" | "processing" | "done" | "error";

export interface JobFile {
  id: string;
  name: string;
  output_name: string | null;
  status: FileStatus;
  progress: number;
  error: string | null;
  width: number;
  height: number;
  output_width: number;
  output_height: number;
}

export interface Job {
  id: string;
  scale: Scale;
  status: "queued" | "processing" | "done";
  progress: number;
  files: JobFile[];
}

export interface Limits {
  scales: Scale[];
  max_file_bytes: number;
  max_files: number;
  max_input_side: Record<string, number>;
  formats: string[];
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(BASE + path, init);
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(body?.detail ?? `Request failed (${res.status})`);
  }
  return res.json();
}

export const getLimits = () => request<Limits>("/api/config");

export function createJob(files: File[], scale: Scale) {
  const form = new FormData();
  form.append("scale", String(scale));
  files.forEach((f) => form.append("files", f));
  return request<Job>("/api/jobs", { method: "POST", body: form });
}

export const getJob = (id: string) => request<Job>(`/api/jobs/${id}`);

export const fileUrl = (jobId: string, fileId: string) => `${BASE}/api/jobs/${jobId}/files/${fileId}`;
export const originalUrl = (jobId: string, fileId: string) => `${BASE}/api/jobs/${jobId}/original/${fileId}`;
export const zipUrl = (jobId: string) => `${BASE}/api/jobs/${jobId}/zip`;
