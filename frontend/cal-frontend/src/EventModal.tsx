import { useState } from "react";
import type { AxiosError } from "axios";
import type { EventOut, EventIn } from "./api";
import { createEvent, updateEvent, deleteEvent } from "./api";

interface Props {
  initial?: EventOut | null;
  onClose(): void;
  onSaved(e: EventOut, mode: "create" | "update" | "delete"): void;
}

const WEEK = ["Sun","Mon","Tue","Wed","Thu","Fri","Sat"] as const;

export default function EventModal({ initial, onClose, onSaved }: Props) {
  const isoNow = new Date().toISOString().slice(0, 16); // yyyy-mm-ddThh:mm

  const [form, setForm] = useState<EventIn>({
    title: initial?.title ?? "",
    start: (initial?.start ?? isoNow).slice(0, 16),
    end: (initial?.end ?? isoNow).slice(0, 16),
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

  // --- Repeat controls (v1) -----------------------------------------
  const [repeatOpen, setRepeatOpen] = useState(false);
  const [repeatDays, setRepeatDays] = useState<Record<number, boolean>>({
    0: false, 1: false, 2: false, 3: false, 4: false, 5: false, 6: false,
  });
  const [repeatUntil, setRepeatUntil] = useState<string>(""); // yyyy-mm-dd

  const toggleDay = (d: number) =>
    setRepeatDays({ ...repeatDays, [d]: !repeatDays[d] });

  const anyRepeat = Object.values(repeatDays).some(Boolean) && !!repeatUntil;

  // Helpers
  const isoWithSeconds = (s: string) =>
    s.length === 16 ? s + ":00" : s; // normalize yyyy-mm-ddThh:mm[:ss]

  const sameTimeOnDate = (baseStartIso: string, baseEndIso: string, ymd: string) => {
    const [datePart] = baseStartIso.split("T");
    const startTime = baseStartIso.slice(datePart.length + 1); // hh:mm[:ss]
    const endDuration =
      new Date(isoWithSeconds(baseEndIso)).getTime() -
      new Date(isoWithSeconds(baseStartIso)).getTime();

    const startIso = `${ymd}T${startTime}`;
    const endIso = new Date(new Date(startIso).getTime() + endDuration)
      .toISOString()
      .slice(0, 19);
    return { startIso: startIso.slice(0, 19), endIso };
  };

  const enumerateRepeats = (): EventIn[] => {
    const start0 = new Date(isoWithSeconds(form.start));
    const until = new Date(repeatUntil + "T23:59:59");
    const out: EventIn[] = [];

    for (let d = new Date(start0); d <= until; d.setDate(d.getDate() + 1)) {
      const dow = d.getDay();
      if (!repeatDays[dow]) continue;

      const ymd = d.toISOString().slice(0, 10);
      const { startIso, endIso } = sameTimeOnDate(form.start, form.end, ymd);
      out.push({ title: form.title, start: startIso, end: endIso });
    }

    // If none selected matched the very first day but user expected it,
    // that's by design: only checked weekdays are generated.
    return out;
  };

  // ------------------------------------------------------------------

  const handleSave = async () => {
    const payload: EventIn = {
      ...form,
      start: isoWithSeconds(form.start),
      end: isoWithSeconds(form.end),
    };

    try {
      if (!isEdit && anyRepeat) {
        // Create many occurrences
        const batch = enumerateRepeats();
        if (batch.length === 0) {
          alert("No matching days between start and until.");
          return;
        }
        for (const ev of batch) {
          try {
            const saved = await createEvent(ev);
            // keep jumping calendar to the latest saved date
            onSaved(saved, "create");
          } catch (err: any) {
            if ((err as AxiosError)?.response?.status === 409) {
              const data: any = (err as AxiosError).response?.data;
              setConflict(data?.detail?.conflicts?.[0] ?? null);
              return; // stop on first conflict
            } else {
              console.error(err);
              alert("Couldn’t save one of the repeats. Check the console.");
              return;
            }
          }
        }
        onClose();
        return;
      }

      // Single create / update
      const saved = isEdit
        ? await updateEvent((initial as EventOut).id, payload)
        : await createEvent(payload);

      setConflict(null);
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
      <div className="bg-white rounded shadow p-6 w-96 space-y-4">
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

        {/* Repeat (v1) */}
        {!isEdit && (
          <div className="border-t pt-3">
            <button
              type="button"
              onClick={() => setRepeatOpen(!repeatOpen)}
              className="text-sm underline"
            >
              {repeatOpen ? "Hide repeat" : "Repeat…"}
            </button>

            {repeatOpen && (
              <div className="mt-3 space-y-3">
                <div className="flex flex-wrap gap-2">
                  {WEEK.map((lbl, i) => (
                    <label key={lbl} className="text-sm inline-flex items-center gap-1">
                      <input
                        type="checkbox"
                        checked={!!repeatDays[i]}
                        onChange={() => toggleDay(i)}
                      />
                      {lbl}
                    </label>
                  ))}
                </div>

                <label className="block text-sm">
                  <span className="text-sm">Until</span>
                  <input
                    type="date"
                    className="mt-1 w-full border rounded px-2 py-1"
                    value={repeatUntil}
                    onChange={(e) => setRepeatUntil(e.target.value)}
                  />
                </label>

                <p className="text-xs text-gray-500">
                  We’ll create an event on each selected weekday through the “until” date,
                  preserving your start/end times.
                </p>
              </div>
            )}
          </div>
        )}

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