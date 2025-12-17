import { useEffect, useState } from "react";
import type { AxiosError } from "axios";
import type { EventOut, EventIn } from "./api";
import { createEvent, updateEvent, deleteEvent, suggestNext } from "./api";
import { isoToLocalInput, localInputToISO, nowLocalInput } from "./datetime";
import { BASE_URL } from "./api";

interface Props {
  initial?: EventOut | null;  // optional seed values (may include thumb/repeat hints)
  onClose(): void;
  onSaved(e: EventOut, mode: "create" | "update" | "delete"): void;
}

const WEEK = ["Sun","Mon","Tue","Wed","Thu","Fri","Sat"] as const;

export default function EventModal({ initial, onClose, onSaved }: Props) {
  // yyyy-mm-ddThh:mm in the user's local time
  const isoNowLocal = nowLocalInput();

  const [form, setForm] = useState<EventIn>({
    title: initial?.title ?? "",
    start: initial?.start ? isoToLocalInput(initial.start) : isoNowLocal,
    end:   initial?.end   ? isoToLocalInput(initial.end)   : isoNowLocal,
  });

  const [conflict, setConflict] = useState<null | { title: string; start: string; end: string }>(null);
  const [suggested, setSuggested] = useState<null | { start: string; end: string }>(null);

  const isEdit = typeof initial?.id === "number" && initial.id !== 0;

  const change =
    (k: keyof EventIn) =>
    (e: React.ChangeEvent<HTMLInputElement>) =>
      setForm({ ...form, [k]: e.target.value });

  // Optional repeat hints passed from NewEventModal
  const providedDays   = (initial as any)?.repeatDays as number[] | undefined;
  const providedUntil  = (initial as any)?.repeatUntil as string | undefined;
  const providedEvery  = (initial as any)?.repeatEveryWeeks as number | undefined;

  const [repeatOpen, setRepeatOpen] = useState(false);
  const [repeatDays, setRepeatDays] = useState<Record<number, boolean>>({0:false,1:false,2:false,3:false,4:false,5:false,6:false});
  const [repeatUntil, setRepeatUntil] = useState<string>(""); // yyyy-mm-dd

  useEffect(() => {
    if ((providedDays && providedDays.length) || providedUntil) setRepeatOpen(true);
    if (providedDays?.length) {
      setRepeatDays(prev => {
        const m = { ...prev };
        providedDays.forEach(d => { if (d >= 0 && d <= 6) m[d] = true; });
        return m;
      });
    }
    if (providedUntil) setRepeatUntil(providedUntil);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const toggleDay = (d: number) => setRepeatDays({ ...repeatDays, [d]: !repeatDays[d] });
  const anyRepeat = Object.values(repeatDays).some(Boolean) && !!repeatUntil;

  const asUTC = (s: string) => localInputToISO(s);

  // Keep same local HH:MM but move to a different date (ymd)
  const sameTimeOnDate = (baseStartLocal: string, baseEndLocal: string, ymd: string) => {
    const startTime = baseStartLocal.split("T")[1]; // hh:mm
    const endTime   = baseEndLocal.split("T")[1];
    const startISO  = localInputToISO(`${ymd}T${startTime}`);
    const endISO    = localInputToISO(`${ymd}T${endTime}`);
    return { startISO, endISO };
  };

  // Expand repeats into concrete occurrences
  const enumerateRepeats = (): EventIn[] => {
    const start0UTC = new Date(asUTC(form.start));
    const until     = repeatUntil ? new Date(`${repeatUntil}T23:59:59`) : null;
    const out: EventIn[] = [];
    if (!until) return out;

    const firstLocalNoon = new Date(
      start0UTC.getUTCFullYear(), start0UTC.getUTCMonth(), start0UTC.getUTCDate(), 12, 0, 0
    );

    const d = new Date(start0UTC);
    for (;;) {
      const localNoon = new Date(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate(), 12, 0, 0);
      if (localNoon > until) break;

      const dow = localNoon.getDay();
      if (repeatDays[dow]) {
        if (providedEvery && providedEvery > 1) {
          const weeksSinceStart = Math.floor((localNoon.getTime() - firstLocalNoon.getTime()) / (7 * 24 * 3600 * 1000));
          if (weeksSinceStart % providedEvery !== 0) { d.setUTCDate(d.getUTCDate() + 1); continue; }
        }
        const y = localNoon.getFullYear();
        const m = String(localNoon.getMonth() + 1).padStart(2, "0");
        const day = String(localNoon.getDate()).padStart(2, "0");
        const ymd = `${y}-${m}-${day}`;

        const { startISO, endISO } = sameTimeOnDate(form.start, form.end, ymd);
        out.push({ title: form.title, start: startISO, end: endISO });
      }
      d.setUTCDate(d.getUTCDate() + 1);
    }
    return out;
  };

  const applySuggestion = (s: { start: string; end: string }) => {
    setForm({ ...form, start: isoToLocalInput(s.start), end: isoToLocalInput(s.end) });
    setConflict(null);
    setSuggested(null);
  };

  const handleSave = async () => {
    const payload: EventIn = { ...form, start: asUTC(form.start), end: asUTC(form.end) };

    try {
      if (!isEdit && anyRepeat) {
        const batch = enumerateRepeats();
        if (batch.length === 0) { alert("No matching days between start and until."); return; }
        for (const ev of batch) {
          try {
            const saved = await createEvent(ev);
            onSaved(saved, "create");
          } catch (err: any) {
            if ((err as AxiosError)?.response?.status === 409) {
              const data: any = (err as AxiosError).response?.data;
              setConflict(data?.detail?.conflicts?.[0] ?? null);
              try { setSuggested(await suggestNext(ev.start, ev.end)); } catch {}
              return;
            } else {
              console.error(err);
              alert("Couldn’t save one of the repeats. See console.");
              return;
            }
          }
        }
        onClose();
        return;
      }

      const saved = isEdit
        ? await updateEvent((initial as EventOut).id, payload)
        : await createEvent(payload);

      setConflict(null);
      setSuggested(null);
      onSaved(saved, isEdit ? "update" : "create");
      onClose();
    } catch (err: any) {
      if ((err as AxiosError)?.response?.status === 409) {
        const data: any = (err as AxiosError).response?.data;
        setConflict(data?.detail?.conflicts?.[0] ?? null);
        try { setSuggested(await suggestNext(payload.start, payload.end)); } catch {}
      } else {
        console.error(err);
        alert("Couldn’t save. See console for details.");
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
              {new Date(conflict.start).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })} – {new Date(conflict.end).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
            </p>

            {suggested && (
              <div className="mt-2 flex items-center gap-2">
                <span className="text-sm">
                  Next free:{" "}
                  {new Date(suggested.start).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}
                  {" – "}
                  {new Date(suggested.end).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                </span>
                <button type="button" onClick={() => applySuggestion(suggested)} className="ml-auto px-2 py-0.5 rounded bg-black text-white">
                  Use it
                </button>
              </div>
            )}
          </div>
        )}

        <div className="flex items-center space-x-3">
          {initial && (initial as any).thumb && (() => {
            const t = (initial as any).thumb as string;
            const src = t.startsWith("http") ? t : `${BASE_URL}${t}`;
            return <img src={src} alt="upload preview" className="w-12 h-12 object-cover rounded" />;
          })()}
          <h2 className="text-xl font-semibold flex-1">{isEdit ? "Edit Event" : "New Event"}</h2>
        </div>

        <label className="block">
          <span className="text-sm">Title</span>
          <input className="mt-1 w-full border rounded px-2 py-1" value={form.title} onChange={change("title")} />
        </label>

        <label className="block">
          <span className="text-sm">Start</span>
          <input type="datetime-local" className="mt-1 w-full border rounded px-2 py-1" value={form.start} onChange={change("start")} />
        </label>

        <label className="block">
          <span className="text-sm">End</span>
          <input type="datetime-local" className="mt-1 w-full border rounded px-2 py-1" value={form.end} onChange={change("end")} />
        </label>

        {!isEdit && (
          <div className="border-t pt-3">
            <button type="button" onClick={() => setRepeatOpen(!repeatOpen)} className="text-sm underline">
              {repeatOpen ? "Hide repeat" : "Repeat…"}
            </button>

            {repeatOpen && (
              <div className="mt-3 space-y-3">
                <div className="flex flex-wrap gap-2">
                  {WEEK.map((lbl, i) => (
                    <label key={lbl} className="text-sm inline-flex items-center gap-1">
                      <input type="checkbox" checked={!!(repeatDays as any)[i]} onChange={() => toggleDay(i)} />
                      {lbl}
                    </label>
                  ))}
                </div>

                <label className="block text-sm">
                  <span className="text-sm">Until</span>
                  <input type="date" className="mt-1 w-full border rounded px-2 py-1" value={repeatUntil} onChange={(e) => setRepeatUntil(e.target.value)} />
                </label>

                <p className="text-xs text-gray-500">Creates an event on each selected weekday through the “until” date, preserving times.</p>
              </div>
            )}
          </div>
        )}

        <div className="flex justify-between pt-3">
          {isEdit && (
            <button type="button" onClick={handleDelete} className="text-red-600 hover:underline">
              Delete
            </button>
          )}
          <div className="ml-auto space-x-2">
            <button type="button" onClick={onClose} className="px-3 py-1">Cancel</button>
            <button type="button" onClick={handleSave} className="bg-black text-white px-3 py-1 rounded">Save</button>
          </div>
        </div>
      </div>
    </div>
  );
}