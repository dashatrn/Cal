import { useState } from "react";
import type { EventOut, EventIn } from "./api";
import { createEvent, updateEvent, deleteEvent } from "./api";

interface Props {
  initial?: EventOut | null;          // accepts undefined, null, or EventOut
  onClose(): void;
  onSaved(e: EventOut, mode: "create" | "update" | "delete"): void;
}

/* rest of file unchanged */
export default function EventModal({ initial, onClose, onSaved }: Props) {
  // local form state

 const isoNow = new Date().toISOString().slice(0, 16); // YYYY-MM-DDTHH:MM
 const [form, setForm] = useState<EventIn>({
   title: initial?.title ?? "",
   start: initial?.start ?? isoNow,
   end:   initial?.end   ?? isoNow,
 });
  const onChange = (k: keyof EventIn) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm({ ...form, [k]: e.target.value });

  const handleSave = async () => {
    if (initial) {
      const saved = await updateEvent(initial.id, form);
      onSaved(saved, "update");
    } else {
      const saved = await createEvent(form);
      onSaved(saved, "create");
    }
    onClose();
  };

  const handleDelete = async () => {
    if (!initial) return;
    await deleteEvent(initial.id);
    onSaved(initial, "delete");
    onClose();
  };

  return (
    <div className="fixed inset-0 grid place-items-center bg-black/40 z-20">
      <div className="bg-white rounded shadow p-6 w-80 space-y-4">
        <h2 className="text-xl font-semibold">
          {initial ? "Edit Event" : "New Event"}
        </h2>

        <label className="block">
          <span className="text-sm">Title</span>
          <input
            className="mt-1 w-full border rounded px-2 py-1"
            value={form.title}
            onChange={onChange("title")}
          />
        </label>

        <label className="block">
          <span className="text-sm">Start (ISO)</span>
          <input
            className="mt-1 w-full border rounded px-2 py-1"
            type="datetime-local"
            value={form.start}
            onChange={onChange("start")}
          />
        </label>

        <label className="block">
          <span className="text-sm">End (ISO)</span>
          <input
            className="mt-1 w-full border rounded px-2 py-1"
            type="datetime-local"
            value={form.end}
            onChange={onChange("end")}
          />
        </label>

        <div className="flex justify-between pt-3">
          {initial && (
            <button
              onClick={handleDelete}
              className="text-red-600 hover:underline"
            >
              Delete
            </button>
          )}
          <div className="ml-auto space-x-2">
            <button onClick={onClose} className="px-3 py-1">Cancel</button>
            <button
              onClick={handleSave}
              className="bg-black text-white px-3 py-1 rounded"
            >
              Save
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}