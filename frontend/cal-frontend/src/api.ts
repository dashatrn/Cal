// src/api.ts
import axios from "axios";

// build-time value from .env  (works in production builds & PWAs)
const envURL = import.meta.env.VITE_API_URL as string | undefined;

// dev-time heuristic (when you’re on https://…-5173.app.github.dev)
const devURL = `${window.location.protocol}//${window.location.hostname.replace("-5173", "-8000")}`;

// final choice
const BASE_URL = (envURL ?? devURL).replace(/\/+$/, "");  // strip trailing “/”

export const api = axios.create({
  baseURL: BASE_URL,
  headers: { "Content-Type": "application/json" },
});

export interface EventIn  { title: string; start: string; end: string }
export interface EventOut extends EventIn { id: number }

export const listEvents  = ()                   => api.get <EventOut[]>("/events").then(r => r.data);
export const createEvent = (e: EventIn)         => api.post<EventOut> ("/events",        e).then(r => r.data);
export const updateEvent = (id: number, e: EventIn) => api.put <EventOut> (`/events/${id}`, e).then(r => r.data);
export const deleteEvent = (id: number)         => api.delete        (`/events/${id}`);