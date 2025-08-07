// ---- src/NewEventModal.tsx ---------------------------------------------
import { useState } from "react";
import clsx from "clsx";

interface Props {
  open: boolean;
  onClose(): void;
  onSubmit(p: { prompt: string; files: File[] }): void;
}

export default function NewEventModal({ open, onClose, onSubmit }: Props) {
  const [prompt, setPrompt] = useState("");
  const [files,  setFiles]  = useState<File[]>([]);

  if (!open) return null;

  const drop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    if (e.dataTransfer.files.length)
      setFiles(Array.from(e.dataTransfer.files));
  };

  return (
    <div className="fixed inset-0 z-20 grid place-items-center bg-black/40">
      <div
        className="bg-white w-[min(90vw,480px)] rounded shadow p-6 space-y-4"
        onDragOver={(e) => e.preventDefault()}
        onDrop={drop}
      >
        {/* drag-area */}
        <div
          className={clsx(
            "border-2 border-dashed rounded h-48 grid place-items-center",
            files.length ? "border-green-400" : "border-gray-300"
          )}
        >
          {files.length
            ? `${files.length} file${files.length > 1 ? "s" : ""} selected`
            : "Drag & drop image(s) here"}
        </div>

        {/* prompt box */}
        <textarea
          placeholder="Tell Cal what to do…"
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          className="w-full border rounded p-2 h-24 resize-none"
        />

        <div className="flex justify-end gap-2">
          <button onClick={onClose} className="px-3 py-1">Cancel</button>
          <button
            onClick={() => {
              onSubmit({ prompt, files });
              setPrompt("");
              setFiles([]);
            }}
            className="bg-black text-white px-3 py-1 rounded"
          >
            Submit
          </button>
        </div>
      </div>
    </div>
  );
}