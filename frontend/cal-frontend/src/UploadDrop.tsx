import { createEvent } from "./api";
import type { EventOut } from "./api";

interface Props {
  onPrefill(e: EventOut): void;
}

export default function UploadDrop({ onPrefill }: Props) {
  const handleFile = async (f: File) => {
    const body = new FormData();
    body.append("file", f);
    const res = await fetch("/uploads", {                // dev-proxy handles origin
      method: "POST",
      body,
    });
    if (!res.ok) {
      alert("Could not parse that image 😢");
      return;
    }
    onPrefill(await res.json());
  };

  return (
    <label className="cursor-pointer bg-gray-200 px-3 py-1 rounded text-sm">
      📷 Upload
      <input
        type="file"
        accept="image/*"
        hidden
        onChange={(e) => {
          if (e.target.files?.[0]) handleFile(e.target.files[0]);
        }}
      />
    </label>
  );
}