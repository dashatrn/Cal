// src/api.ts
import axios from "axios";

const envURL = import.meta.env.VITE_API_URL as string | undefined;
const devURL = `${window.location.protocol}//${window.location.hostname.replace("-5173", "-8000")}`;
const BASE_URL = (envURL ?? devURL).replace(/\/+$/, "");

export const api = axios.create({
  baseURL: BASE_URL,
  headers: { "Content-Type": "application/json" },
});

// Event models (naive/local datetimes)
export interface EventIn  { title: string; start: string; end: string }
export interface EventOut extends EventIn { id: number }

// Calendar CRUD
export const listEvents  = ()                         => api.get <EventOut[]>("/events").then(r => r.data);
export const createEvent = (e: EventIn)               => api.post<EventOut> ("/events",        e).then(r => r.data);
export const updateEvent = (id: number, e: EventIn)   => api.put <EventOut> (`/events/${id}`,  e).then(r => r.data);
export const deleteEvent = (id: number)               => api.delete        (`/events/${id}`);

// Parsing helpers
export type ParsedFields = Partial<EventIn> & {
  thumb?: string;
  repeatDays?: number[];      // 0=Sun..6=Sat
  repeatUntil?: string;       // YYYY-MM-DD
};

// Use fetch for multipart so we don’t fight axios JSON headers
export async function uploadImageForParse(file: File): Promise<ParsedFields> {
  const body = new FormData();
  body.append("file", file);
  const res = await fetch(`${BASE_URL}/uploads`, { method: "POST", body });
  if (!res.ok) throw new Error("upload failed");
  return res.json();
}

export const parsePrompt = (prompt: string) =>
  api.post<ParsedFields>("/parse", { prompt }).then(r => r.data);