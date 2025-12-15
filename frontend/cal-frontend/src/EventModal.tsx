import React, { useEffect, useMemo, useState } from "react";
import { createEvent, createSeries, updateEvent, deleteEvent, suggestNext } from "./api";

type Mode = "create" | "edit";

type Props = {
  isOpen: boolean;
  initial?: any;
  parsed?: any;
  onClose: () => void;
  onSaved: (evt?: any, mode?: Mode) => void;
};

function toLocalInputValue(iso: string) {
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, "0");
  const yyyy = d.getFullYear();
  const mm = pad(d.getMonth() + 1);
  const dd = pad(d.getDate());
  const hh = pad(d.getHours());
  const mi = pad(d.getMinutes());
  return `${yyyy}-${mm}-${dd}T${hh}:${mi}`;
}

function asUTC(yyyyMMddThhmm: string) {
  const d = new Date(yyyyMMddThhmm);
  return d.toISOString();
}

function weekdayFromISO(iso: string) {
  const d = new Date(iso);
  // Convert JS getDay() (0=Sun..6=Sat) to our same convention
  return d.getDay();
}

export default function EventModal({ isOpen, initial, parsed, onClose, onSaved }: Props) {
  const isEdit = !!initial?.id;

  const [title, setTitle] = useState("");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [description, setDescription] = useState("");
  const [location, setLocation] = useState("");

  const [repeatUntil, setRepeatUntil] = useState<string>("");
  const [repeatDays, setRepeatDays] = useState<Record<number, boolean>>({});
  const providedDays: number[] | undefined = parsed?.repeatDays;
  const providedUntil: string | undefined = parsed?.repeatUntil;
  const providedEvery: number | undefined = parsed?.repeatEveryWeeks;

  useEffect(() => {
    if (!isOpen) return;

    const src = initial || parsed || {};
    setTitle(src.title || "");
    setStart(src.start ? toLocalInputValue(src.start) : "");
    setEnd(src.end ? toLocalInputValue(src.end) : "");
    setDescription(src.description || "");
    setLocation(src.location || "");

    // seed recurrence from parsed hints
    if (!isEdit && providedUntil) setRepeatUntil(providedUntil);
    if (!isEdit && providedDays?.length) {
      const map: Record<number, boolean> = {};
      for (const d of providedDays) map[d] = true;
      setRepeatDays(map);
    } else if (!isEdit && src.start) {
      const wd = weekdayFromISO(src.start);
      setRepeatDays({ [wd]: true });
    }
  }, [isOpen]);

  const anyRepeat = useMemo(() => {
    const hasDay = Object.values(repeatDays).some(Boolean);
    return !!repeatUntil && hasDay;
  }, [repeatUntil, repeatDays]);

  function toggleDay(d: number) {
    setRepeatDays((prev) => ({ ...prev, [d]: !prev[d] }));
  }

  function enumerateRepeats() {
    // Keeps the old client-side logic around (not used anymore for creation),
    // but can be useful for debugging or later UI work.
    const days = Object.entries(repeatDays)
      .filter(([_, v]) => v)
      .map(([k]) => Number(k));
    if (!repeatUntil || days.length === 0 || !start || !end) return [];

    const startIso = asUTC(start);
    const endIso = asUTC(end);

    const startDate = new Date(startIso);
    const untilDate = new Date(`${repeatUntil}T23:59:59`);

    const durMs = new Date(endIso).getTime() - new Date(startIso).getTime();
    const out: any[] = [];

    // crude weekly stepping
    let cursor = new Date(startDate);
    while (cursor <= untilDate) {
      const dow = cursor.getDay(); // 0..6
      if (days.includes(dow)) {
        const occStart = new Date(cursor);
        // force same time as original start
        const src = new Date(startIso);
        occStart.setHours(src.getHours(), src.getMinutes(), 0, 0);
        const occEnd = new Date(occStart.getTime() + durMs);

        out.push({
          title,
          start: occStart.toISOString(),
          end: occEnd.toISOString(),
          description,
          location,
        });
      }
      cursor.setDate(cursor.getDate() + 1);
    }
    return out;
  }

  const handleSuggest = async () => {
    try {
      const s = asUTC(start);
      const e = asUTC(end);
      const r = await suggestNext(s, e);
      setStart(toLocalInputValue(r.start));
      setEnd(toLocalInputValue(r.end));
    } catch (err) {
      alert("No free slot found.");
    }
  };

  const handleSave = async () => {
    try {
      const payload = {
        title,
        start: asUTC(start),
        end: asUTC(end),
        description: description || null,
        location: location || null,
      };

      if (!isEdit && anyRepeat) {
        const days = Object.entries(repeatDays)
          .filter(([_, v]) => v)
          .map(([k]) => Number(k));

        if (days.length === 0 || !repeatUntil) {
          alert("No matching days between start and until.");
          return;
        }

        const tz = Intl.DateTimeFormat().resolvedOptions().timeZone;
        const every = (providedEvery && providedEvery > 0) ? providedEvery : 1;

        const created = await createSeries({
          title: payload.title,
          start: payload.start,
          end: payload.end,
          description: payload.description ?? null,
          location: payload.location ?? null,
          repeatDays: days,
          repeatEveryWeeks: every,
          repeatUntil,
          tz,
        });

        // Trigger a reload + jump once (App ignores the mode arg)
        onSaved(created.events?.[0], "create");
        onClose();
        return;
      }

      if (isEdit) {
        const saved = await updateEvent(initial.id, payload);
        onSaved(saved, "edit");
      } else {
        const saved = await createEvent(payload);
        onSaved(saved, "create");
      }

      onClose();
    } catch (err: any) {
      if (err?.response?.status === 409) {
        alert("That time overlaps another event.");
      } else {
        alert("Failed to save event.");
      }
    }
  };

  const handleDelete = async () => {
    if (!isEdit) return;
    if (!confirm("Delete this event?")) return;

    try {
      await deleteEvent(initial.id);
      onSaved(undefined, "edit");
      onClose();
    } catch (err) {
      alert("Failed to delete.");
    }
  };

  if (!isOpen) return null;

  return (
    <div className="modal-backdrop">
      <div className="modal">
        <h2 className="modal-title">{isEdit ? "Edit Event" : "New Event"}</h2>

        <label className="field">
          <span>Title</span>
          <input value={title} onChange={(e) => setTitle(e.target.value)} />
        </label>

        <label className="field">
          <span>Start</span>
          <input type="datetime-local" value={start} onChange={(e) => setStart(e.target.value)} />
        </label>

        <label className="field">
          <span>End</span>
          <input type="datetime-local" value={end} onChange={(e) => setEnd(e.target.value)} />
        </label>

        <label className="field">
          <span>Description</span>
          <textarea value={description} onChange={(e) => setDescription(e.target.value)} />
        </label>

        <label className="field">
          <span>Location</span>
          <input value={location} onChange={(e) => setLocation(e.target.value)} />
        </label>

        {!isEdit && (
          <div className="repeat-box">
            <div className="repeat-row">
              <span>Repeat on:</span>
              <div className="repeat-days">
                {["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].map((lab, idx) => (
                  <button
                    key={lab}
                    className={repeatDays[idx] ? "day on" : "day"}
                    onClick={() => toggleDay(idx)}
                    type="button"
                  >
                    {lab}
                  </button>
                ))}
              </div>
            </div>

            <div className="repeat-row">
              <span>Until:</span>
              <input
                type="date"
                value={repeatUntil}
                onChange={(e) => setRepeatUntil(e.target.value)}
              />
            </div>

            {providedEvery && providedEvery > 1 ? (
              <div className="repeat-hint">Every {providedEvery} weeks (from parsed text)</div>
            ) : null}
          </div>
        )}

        <div className="actions">
          <button type="button" onClick={handleSuggest}>
            Suggest next-free
          </button>

          <div className="actions-right">
            {isEdit ? (
              <button type="button" onClick={handleDelete}>
                Delete
              </button>
            ) : null}
            <button type="button" onClick={onClose}>
              Cancel
            </button>
            <button type="button" onClick={handleSave}>
              Save
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}