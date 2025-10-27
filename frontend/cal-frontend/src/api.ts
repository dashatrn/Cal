// src/api.ts
import axios from "axios";

/**
 * API base URL:
 * - Prefer Vite build-time env (VITE_API_URL).
 * - Fall back to your deployed API URL to keep the app functional if env is missing.
 */
let BASE_URL =
  (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/+$/, "") ||
  "https://cal-api-otk8.onrender.com"; // <-- replace with YOUR API External URL

if (!/^https?:\/\//i.test(BASE_URL)) {
  console.error("[cal] Invalid BASE_URL:", BASE_URL);
}

export { BASE_URL };

/**
 * Let axios pick headers per request.
 * Don't set a global Content-Type to avoid unnecessary preflights.
 */
export const api = axios.create({ baseURL: BASE_URL });

export interface EventIn {
  title: string;
  start: string;
  end:   string;
  description?: string | null;
  location?: string | null;
}
export interface EventOut extends EventIn { id: number }

export const listEvents  = (start?: string, end?: string) =>
  api.get<EventOut[]>("/events", { params: (start && end) ? { start, end } : undefined })
     .then(r => r.data);

export const createEvent = (e: EventIn)             =>
  api.post<EventOut> ("/events",        e).then(r => r.data);

export const updateEvent = (id: number, e: EventIn) =>
  api.put <EventOut> (`/events/${id}`,  e).then(r => r.data);

export const deleteEvent = (id: number) =>
  api.delete(`/events/${id}`);

export type ParsedFields = Partial<EventIn> & {
  thumb?: string;
  repeatDays?: number[];
  repeatUntil?: string;      // YYYY-MM-DD (local)
  repeatEveryWeeks?: number; // e.g. 2 for biweekly
};

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

export const suggestNext = (startIso: string, endIso: string) =>
  api.get<{ start: string; end: string }>("/suggest", { params: { start: startIso, end: endIso } })
     .then(r => r.data);