import { useDropzone, type FileRejection } from "react-dropzone";

interface Props {
  onFiles: (files: File[]) => void;
  onReject: (message: string) => void;
  maxSize: number;
  disabled?: boolean;
}

const ACCEPT = { "image/jpeg": [".jpg", ".jpeg"], "image/png": [".png"], "image/webp": [".webp"] };

export default function Dropzone({ onFiles, onReject, maxSize, disabled }: Props) {
  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    accept: ACCEPT,
    maxSize,
    multiple: true,
    disabled,
    onDrop: (accepted: File[], rejected: FileRejection[]) => {
      if (accepted.length) onFiles(accepted);
      if (rejected.length) {
        const r = rejected[0];
        const reason = r.errors[0]?.code === "file-too-large"
          ? `larger than ${Math.round(maxSize / 1024 / 1024)} MB`
          : "not a JPG, PNG or WEBP image";
        const more = rejected.length > 1 ? ` (and ${rejected.length - 1} more)` : "";
        onReject(`${r.file.name} was skipped: ${reason}${more}`);
      }
    },
  });

  return (
    <div
      {...getRootProps()}
      className={`flex cursor-pointer flex-col items-center justify-center rounded-2xl border-2 border-dashed px-6 py-12 text-center transition ${
        isDragActive ? "border-indigo-500 bg-indigo-50" : "border-slate-300 bg-white hover:border-indigo-400"
      } ${disabled ? "pointer-events-none opacity-60" : ""}`}
    >
      <input {...getInputProps()} data-testid="file-input" />
      <svg className="mb-3 h-10 w-10 text-indigo-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5m-13.5-9L12 3m0 0l4.5 4.5M12 3v13.5" />
      </svg>
      <p className="text-base font-semibold text-slate-800">
        {isDragActive ? "Drop images here" : "Drag & drop images, or click to browse"}
      </p>
      <p className="mt-1 text-sm text-slate-500">
        JPG, PNG or WEBP · up to {Math.round(maxSize / 1024 / 1024)} MB each · add several for batch processing
      </p>
    </div>
  );
}
