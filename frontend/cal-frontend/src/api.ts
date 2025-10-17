// src/api.ts
import axios from "axios";

// 1) Prefer Render's build-time env
let BASE_URL = (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/+$/, "");

// 2) If missing (mis-built frontend), hard fallback to your live API
if (!BASE_URL && typeof window !== "undefined") {
  const here = window.location.origin.replace(/\/+$/, "");
  if (here === "https://cal-frontend-4k1s.onrender.com") {
    BASE_URL = "https://cal-api-otk8.onrender.com";
  }
}

// 3) Final guard: fail loudly so you see it in the console instead of “ERR_NETWORK”
if (!BASE_URL) {
  console.error("[cal] VITE_API_URL is missing and no safe fallback matched. Set VITE_API_URL.");
  // optional: throw or keep as "" — I recommend throw so you notice immediately:
  // throw new Error("VITE_API_URL missing");
  BASE_URL = ""; // keep if you prefer not to throw
}

export { BASE_URL };

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