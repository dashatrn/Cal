import { useCallback } from "react";
import type { EventOut } from "./api";

interface Props {
  onPrefill(e: EventOut): void;
}

export default function UploadDrop({ onPrefill }: Props) {
  const handleFile = async (f: File) => {
    const form = new FormData();
    form.append("file", f);
    const res = await fetch("/uploads", { method: "POST", body: form });
    if (!res.ok) return alert("Could not parse that image 😢");
    onPrefill(await res.json());
  };

  /* drag-and-drop handlers */
  const drop = useCallback(
    (e: React.DragEvent<HTMLLabelElement>) => {
      e.preventDefault();
      const f = e.dataTransfer.files?.[0];
      if (f) handleFile(f);
    },
    [],
  );

  return (
    <label
      onDragOver={(e) => e.preventDefault()}
      onDrop={drop}
      className="cursor-pointer bg-gray-200 dark:bg-gray-700 text-gray-800 dark:text-gray-100 px-3 py-1 rounded text-sm select-none"
    >
      📷 Upload
      <input
        type="file"
        accept="image/*"
        hidden
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) handleFile(f);
        }}
      />
    </label>
  );
}