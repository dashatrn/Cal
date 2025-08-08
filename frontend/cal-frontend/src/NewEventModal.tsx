import { useEffect, useMemo, useRef, useState } from "react";
import { uploadImageForParse, parsePrompt } from "./api";
import type { ParsedFields } from "./api";  // <-- type-only

type PartialEvent = ParsedFields;

interface Props {
  open: boolean;
  onClose(): void;
  onSubmit(e: PartialEvent): void;
}

export default function NewEventModal({ open, onClose, onSubmit }: Props) {
  const [prompt, setPrompt] = useState("");
  const [fromImage, setFromImage] = useState<PartialEvent | null>(null);
  const [fromText, setFromText] = useState<PartialEvent | null>(null);
  const [busy, setBusy] = useState(false);
  const dropRef = useRef<HTMLLabelElement | null>(null);

  useEffect(() => {
    if (!open) return;
    const t = setTimeout(async () => {
      const p = prompt.trim();
      if (!p) return setFromText(null);
      try {
        const parsed = await parsePrompt(p);
        setFromText(parsed);
      } catch (e) {
        console.error(e);
      }
    }, 600);
    return () => clearTimeout(t);
  }, [prompt, open]);

  const handleFiles = async (files: FileList | null) => {
    const f = files?.[0];
    if (!f) return;
    setBusy(true);
    try {
      const parsed = await uploadImageForParse(f);
      setFromImage(parsed);
    } catch (e) {
      console.error(e);
      alert("Could not parse that image 😢");
    } finally {
      setBusy(false);
    }
  };

  const merged: PartialEvent = useMemo(() => {
    const img = fromImage ?? {};
    const txt = fromText ?? {};
    return {
      thumb: img.thumb ?? undefined,
      title: txt.title || img.title,
      start: txt.start || img.start,
      end: txt.end || img.end,
      repeatDays: txt.repeatDays || img.repeatDays,
      repeatUntil: txt.repeatUntil || img.repeatUntil,
    };
  }, [fromImage, fromText]);

  if (!open) return null;

  const dayNames = ["Sun","Mon","Tue","Wed","Thu","Fri","Sat"];

  return (
    <div className="fixed inset-0 z-30 grid place-items-center bg-black/40">
      <div className="w-[680px] max-w-[92vw] bg-white rounded shadow-lg overflow-hidden">
        <div className="px-5 py-4 border-b flex items-center justify-between">
          <h2 className="text-lg font-semibold">New</h2>
          <button onClick={onClose} className="text-sm opacity-70 hover:opacity-100">
            Close
          </button>
        </div>

        <div className="p-5 grid gap-4">
          <label
            ref={dropRef}
            onDragOver={(e) => { e.preventDefault(); e.dataTransfer.dropEffect = "copy"; }}
            onDrop={(e) => { e.preventDefault(); handleFiles(e.dataTransfer.files); }}
            className="relative group grid place-items-center rounded border-2 border-dashed border-gray-300 hover:border-gray-400 min-h-[240px] cursor-pointer bg-gray-50"
          >
            <div className="text-center px-6 py-8">
              <p className="text-sm text-gray-600">
                Drag & drop a screenshot/email here, or click to choose a file
              </p>
              {busy && <p className="text-xs mt-2">Scanning…</p>}
              {fromImage?.thumb && (
                <div className="mt-3 flex items-center gap-2 justify-center">
                  <img className="w-12 h-12 object-cover rounded" src={fromImage.thumb} alt="preview" />
                  <span className="text-xs text-gray-500">image attached</span>
                </div>
              )}
            </div>
            <input
              type="file"
              accept="image/*"
              hidden
              onChange={(e) => handleFiles(e.target.files)}
            />
          </label>

          <div className="grid gap-2">
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium">Describe it</span>
              <div className="relative group">
                <button type="button" className="text-xs px-2 py-1 rounded border bg-white hover:bg-gray-50">
                  Hover for preview
                </button>
                <div className="absolute right-0 mt-2 w-80 rounded border bg-white shadow-lg p-3 text-sm hidden group-hover:block">
                  <p className="font-semibold mb-1">Preview</p>
                  {(merged.title || merged.start || merged.end || merged.repeatDays) ? (
                    <ul className="space-y-1">
                      <li><span className="text-gray-500">Title:</span> {merged.title ?? "—"}</li>
                      <li><span className="text-gray-500">Start:</span> {merged.start ?? "—"}</li>
                      <li><span className="text-gray-500">End:</span> {merged.end ?? "—"}</li>
                      <li>
                        <span className="text-gray-500">Repeat:</span>{" "}
                        {merged.repeatDays?.length ? merged.repeatDays.map(d => dayNames[d]).join(", ") : "—"}
                        {merged.repeatUntil ? ` (until ${merged.repeatUntil})` : ""}
                      </li>
                    </ul>
                  ) : (
                    <p className="text-gray-500">Nothing parsed yet.</p>
                  )}
                </div>
              </div>
            </div>

            <textarea
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              rows={4}
              placeholder={`Examples:
"Brunch with Alex Saturday 10–12"
"CS lecture Mon/Wed 9:30-10:20, repeat until Dec 10"
"Every weekday 7pm to 7:30"
"Move Friday standup to 2pm"
`}
              className="w-full border rounded px-3 py-2 resize-y"
            />
            <p className="text-xs text-gray-500">
              Tip: whatever you type here overrides what was extracted from the image.
            </p>
          </div>
        </div>

        <div className="px-5 py-4 border-t flex justify-end gap-2">
          <button onClick={onClose} className="px-3 py-1">Cancel</button>
          <button onClick={() => onSubmit(merged)} className="px-3 py-1 rounded bg-black text-white">
            Next
          </button>
        </div>
      </div>
    </div>
  );
}