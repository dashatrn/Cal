import { useState, useEffect } from "react";
import type { AxiosError } from "axios";
import type { EventOut, EventIn } from "./api";
import { createEvent, updateEvent, deleteEvent } from "./api";

interface Props {
  initial?: EventOut | null;
  onClose(): void;
  onSaved(e: EventOut, mode: "create" | "update" | "delete"): void;
}

export default function EventModal({ initial, onClose, onSaved }: Props) {
  const isoNow = new Date().toISOString().slice(0, 16); // yyyy-mm-ddThh:mm

  const [form, setForm] = useState<EventIn>({
    title: initial?.title ?? "",
    start: initial?.start?.slice(0, 16) ?? isoNow,
    end: initial?.end?.slice(0, 16) ?? isoNow,
  });

  const [conflict, setConflict] = useState<null | {
    title: string;
    start: string;
    end: string;
  }>(null);

  const isEdit = typeof initial?.id === "number" && initial.id !== 0;
  const change =
    (k: keyof EventIn) =>
    (e: React.ChangeEvent<HTMLInputElement>) =>
      setForm({ ...form, [k]: e.target.value });

  const handleSave = async () => {
    const payload: EventIn = {
      ...form,
      start: form.start.endsWith(":00") ? form.start : form.start + ":00",
      end: form.end.endsWith(":00") ? form.end : form.end + ":00",
    };

    try {
      const saved = isEdit
        ? await updateEvent((initial as EventOut).id, payload)
        : await createEvent(payload);

      setConflict(null); // clear any previous error
      onSaved(saved, isEdit ? "update" : "create");
      onClose();
    } catch (err: any) {
      if ((err as AxiosError)?.response?.status === 409) {
          const data: any = (err as AxiosError).response?.data;
          setConflict(data?.detail?.conflicts?.[0] ?? null);

      } else {
        console.error(err);
        alert("Couldn’t save. Check the browser console for details.");
      }
    }
  };

  const handleDelete = async () => {
    if (!isEdit) return;
    await deleteEvent(initial!.id);
    onSaved(initial!, "delete");
    onClose();
  };

  return (
    <div className="fixed inset-0 grid place-items-center bg-black/40 z-20">
      <div className="bg-white rounded shadow p-6 w-80 space-y-4">
        {conflict && (
          <div className="bg-red-100 text-red-800 p-2 rounded text-sm">
            <p className="font-semibold">⛔ Time conflict</p>
            <p>{conflict.title}</p>
            <p>
              {new Date(conflict.start).toLocaleTimeString([], {
                hour: "2-digit",
                minute: "2-digit",
              })}{" "}
              –{" "}
              {new Date(conflict.end).toLocaleTimeString([], {
                hour: "2-digit",
                minute: "2-digit",
              })}
            </p>
          </div>
        )}

        <div className="flex items-center space-x-3">
          {initial && (initial as any).thumb && (
            <img
              src={(initial as any).thumb}
              alt="upload preview"
              className="w-12 h-12 object-cover rounded"
            />
          )}
          <h2 className="text-xl font-semibold flex-1">
            {isEdit ? "Edit Event" : "New Event"}
          </h2>
        </div>

        <label className="block">
          <span className="text-sm">Title</span>
          <input
            className="mt-1 w-full border rounded px-2 py-1"
            value={form.title}
            onChange={change("title")}
          />
        </label>

        <label className="block">
          <span className="text-sm">Start</span>
          <input
            type="datetime-local"
            className="mt-1 w-full border rounded px-2 py-1"
            value={form.start}
            onChange={change("start")}
          />
        </label>

        <label className="block">
          <span className="text-sm">End</span>
          <input
            type="datetime-local"
            className="mt-1 w-full border rounded px-2 py-1"
            value={form.end}
            onChange={change("end")}
          />
        </label>

        <div className="flex justify-between pt-3">
          {isEdit && (
            <button
              type="button"
              onClick={handleDelete}
              className="text-red-600 hover:underline"
            >
              Delete
            </button>
          )}
          <div className="ml-auto space-x-2">
            <button type="button" onClick={onClose} className="px-3 py-1">
              Cancel
            </button>
            <button
              type="button"
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
