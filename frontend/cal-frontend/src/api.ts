import axios from "axios";

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL ?? "http://localhost:8000",
  headers: { "Content-Type": "application/json" },
});

export interface EventIn  { title: string; start: string; end: string }
export interface EventOut extends EventIn { id: number }

export const listEvents  = ()                     => api.get<EventOut[]>("/events").then(r => r.data);
export const createEvent = (e: EventIn)           => api.post<EventOut>("/events",   e).then(r => r.data);
export const updateEvent = (id: number, e: EventIn) => api.put<EventOut>(`/events/${id}`, e).then(r => r.data);
export const deleteEvent = (id: number)           => api.delete(`/events/${id}`);