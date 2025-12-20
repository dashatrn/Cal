// src/api.ts
import axios from "axios";

const DEV = import.meta.env.DEV;

// In dev: use relative paths and let Vite proxy -> backend:8000 (as in vite.config.ts)
// In prod: use the absolute API URL provided at build time.
const BASE_URL = DEV ? "" : (import.meta.env.VITE_API_URL as string);

export { BASE_URL };
export const api = axios.create({
  baseURL: BASE_URL,
  withCredentials: false, // will flip to true when we move to cookie auth
});

export interface EventIn {
  title: string;
  start: string;
  end: string;
  description?: string | null;
  location?: string | null;

  // Optional recurrence hints (safe even if backend ignores them)
  repeatDays?: number[] | null;
  repeatUntil?: string | null;      // YYYY-MM-DD
  repeatEveryWeeks?: number | null; // e.g. 2 for biweekly
}

export interface EventOut extends EventIn {
  id: number;
}

export const listEvents = (start?: string, end?: string) =>
  api
    .get<EventOut[]>("/events", { params: start && end ? { start, end } : undefined })
    .then((r) => r.data);

export const createEvent = (e: EventIn) =>
  api.post<EventOut>("/events", e).then((r) => r.data);

export const updateEvent = (id: number, e: EventIn) =>
  api.put<EventOut>(`/events/${id}`, e).then((r) => r.data);

export const deleteEvent = (id: number) => api.delete(`/events/${id}`);

export type ParsedFields = Partial<EventIn> & {
  // UI helpers
  thumb?: string;    // absolute (prod) or relative (dev) URL for image preview
  fileUrl?: string;  // backend-served uploaded file path (e.g. "/uploads/abc.png")
  sourceText?: string;
};

function absolutizeMaybe(pathOrUrl: string | undefined): string | undefined {
  if (!pathOrUrl) return undefined;
  if (pathOrUrl.startsWith("http://") || pathOrUrl.startsWith("https://")) return pathOrUrl;
  return `${BASE_URL}${pathOrUrl}`;
}

export async function uploadImageForParse(file: File): Promise<ParsedFields> {
  const body = new FormData();
  body.append("file", file);

  const tz = Intl.DateTimeFormat().resolvedOptions().timeZone;

  const res = await fetch(`${BASE_URL}/uploads?tz=${encodeURIComponent(tz)}`, {
    method: "POST",
    body,
  });
  if (!res.ok) throw new Error("upload failed");

  const data: any = await res.json();

  // Support BOTH shapes:
  // - current backend: { sourceText, fields, fileUrl }
  // - potential future backend: fields directly
  const fields: any = data?.fields ?? data ?? {};
  const fileUrl: string | undefined = data?.fileUrl ?? fields?.fileUrl;

  const isImage = (file.type || "").startsWith("image/");
  const thumb =
    isImage
      ? (absolutizeMaybe(fields?.thumb) ?? absolutizeMaybe(fileUrl))
      : undefined;

  return {
    ...(fields || {}),
    fileUrl,
    sourceText: data?.sourceText ?? fields?.sourceText,
    thumb,
  };
}

export const parsePrompt = (prompt: string, tz?: string) =>
  api
    .post<ParsedFields>("/parse", {
      prompt,
      tz: tz || Intl.DateTimeFormat().resolvedOptions().timeZone,
    })
    .then((r) => r.data);

export const suggestNext = async (startIso: string, endIso: string) => {
  const r = await api.get<any>("/suggest", { params: { start: startIso, end: endIso } });
  const d = r.data;

  // Support backend returning either {start,end} or {suggestedStart,suggestedEnd}
  if (d && typeof d === "object") {
    if (typeof d.start === "string" && typeof d.end === "string") return { start: d.start, end: d.end };
    if (typeof d.suggestedStart === "string" && typeof d.suggestedEnd === "string") {
      return { start: d.suggestedStart, end: d.suggestedEnd };
    }
  }

  return d as { start: string; end: string };
};