// src/api.ts
import axios from "axios";

// Build-time env from Render
const envURLRaw = import.meta.env.VITE_API_URL as string | undefined;

// Fallback for safety (use your live pair)
const fallbackURL =
  typeof window !== "undefined" &&
  window.location.origin === "https://cal-frontend-4k1s.onrender.com"
    ? "https://cal-api-otk8.onrender.com"
    : undefined;

export const BASE_URL = (envURLRaw || fallbackURL || "").replace(/\/+$/, "");

export const api = axios.create({
  baseURL: BASE_URL,
  headers: { "Content-Type": "application/json" },
});

export interface EventIn  {
  title: string;
  start: string;
  end:   string;
  // add these two:
  description?: string | null;
  location?: string | null;
}

export interface EventOut extends EventIn { id: number }
// Calendar CRUD
// NOTE: start/end are optional and safe to send even if the backend ignores them.
export const listEvents  = (start?: string, end?: string) =>
  api.get<EventOut[]>("/events", {
    params: (start && end) ? { start, end } : undefined,
  }).then(r => r.data);

export const createEvent = (e: EventIn)             =>
  api.post<EventOut> ("/events",        e).then(r => r.data);

export const updateEvent = (id: number, e: EventIn) =>
  api.put <EventOut> (`/events/${id}`,  e).then(r => r.data);

export const deleteEvent = (id: number)             =>
  api.delete        (`/events/${id}`);

// Parsed fields returned from /uploads and /parse
export type ParsedFields = Partial<EventIn> & {
  thumb?: string;
  repeatDays?: number[];
  repeatUntil?: string;      // YYYY-MM-DD (local)
  repeatEveryWeeks?: number; // ← NEW
};

// multipart upload
export async function uploadImageForParse(file: File): Promise<ParsedFields> {
  const body = new FormData();
  body.append("file", file);
  const res = await fetch(`${BASE_URL}/uploads`, { method: "POST", body });
  if (!res.ok) throw new Error("upload failed");
  return res.json();
}

export const parsePrompt = (prompt: string, tz?: string) =>
  api.post<ParsedFields>("/parse", {
    prompt,
    tz: tz || Intl.DateTimeFormat().resolvedOptions().timeZone,
  }).then(r => r.data);

// NEW: ask backend for next free suggestion
export const suggestNext = (startIso: string, endIso: string) =>
  api.get<{ start: string; end: string }>("/suggest", { params: { start: startIso, end: endIso } })
     .then(r => r.data);