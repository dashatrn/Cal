import { useEffect, useRef, useState } from "react";
import FullCalendar from "@fullcalendar/react";
import dayGridPlugin from "@fullcalendar/daygrid";
import timeGridPlugin from "@fullcalendar/timegrid";
import interactionPlugin from "@fullcalendar/interaction";
import type { DateClickArg } from "@fullcalendar/interaction";
import type { EventClickArg, EventInput } from "@fullcalendar/core"

import { listEvents } from "./api";
import type { EventOut as ApiEvent } from "./api";
import EventModal from "./EventModal";
import UploadDrop from "./UploadDrop";
import NewEventModal from "./NewEventModal";   // NEW

import "./index.css";   // tailwind styles
import "./App.css";     // component-specific tweaks

type CalEvent = Omit<ApiEvent, "id"> & { id: string };

export default function App() {
  /* ───────────────────────── state / refs ───────────────────────── */
  const [events, setEvents] = useState<CalEvent[]>([]);
  const [modalInit, setModalInit] = useState<ApiEvent | undefined | null>(null);
  const calRef = useRef<FullCalendar | null>(null);
  const [showNew, setShowNew] = useState(false);   // NEW
  /* ───────────────────────── helpers ────────────────────────────── */
  const fetchEvents = () =>
    listEvents()
      .then((api) => setEvents(api.map((e) => ({ ...e, id: e.id.toString() }))))
      .catch(console.error);

  const gotoPrev = () => calRef.current?.getApi().prev();
  const gotoNext = () => calRef.current?.getApi().next();
  const gotoDate  = (iso: string) => calRef.current?.getApi().gotoDate(iso);

  const openCreate = (dateISO?: string) =>
    setModalInit(
      dateISO
        ? { id: 0, title: "", start: dateISO + "T00:00", end: dateISO + "T01:00" }
        : undefined,
    );

  const openEdit = (evt: ApiEvent) => setModalInit(evt);

  const handleSaved = (e?: ApiEvent) => {
    if (e) gotoDate(e.start);
    fetchEvents();
    setModalInit(null);
  };
  

  const handleNewSubmit = (p: { prompt: string; files: File[] }) => {
    console.log("NEW SUBMIT", p);   // we’ll fill this in Phase-2
    setShowNew(false);
  };
  /* ───────────────────────── initial load ───────────────────────── */
  useEffect(() => {
    listEvents()
      .then((api) => {
        const mapped = api.map((e) => ({ ...e, id: e.id.toString() }));
        setEvents(mapped);
        if (mapped.length) gotoDate(mapped[mapped.length - 1].start);
      })
      .catch(console.error);
  }, []);

  /* ───────────────────────── render ─────────────────────────────── */
  return (
    <div className="min-h-screen flex flex-col bg-gray-50 dark:bg-gray-900">
      {/* ── header ─────────────────────────────────────────────── */}
    <header className="h-16 relative flex items-center justify-center bg-white shadow">
      {/* + New – fixed left */}
      <button onClick={() => setShowNew(true)}
              className="absolute left-6 bg-black text-white px-3 py-1 rounded">
        + New
      </button>

      {/* Title – naturally centered because header uses justify-center */}
      <h1 className="text-xl font-semibold select-none">Cal</h1>
    </header>

      {/* ── calendar toolbar (view switch + arrows) ─────────────── */}
      <div className="h-12 flex items-center justify-between px-4 md:px-8 bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700">
        <div className="space-x-1 text-sm">
          {(["dayGridDay", "timeGridWeek", "dayGridMonth"] as const).map((v) => (
            <button
              key={v}
              onClick={() => calRef.current?.getApi().changeView(v)}
              className="px-2 py-1 rounded hover:bg-gray-100 dark:hover:bg-gray-700"
            >
              {v === "dayGridDay" ? "Day" : v === "timeGridWeek" ? "Week" : "Month"}
            </button>
          ))}
        </div>

        <div className="space-x-1">
      <button
        onClick={gotoPrev}
        className="hidden md:grid fixed left-2 top-1/2 -translate-y-1/2
                  w-10 h-10 bg-white rounded-full shadow place-content-center">
        ‹
      </button>

      <button
        onClick={gotoNext}
        className="hidden md:grid fixed right-2 top-1/2 -translate-y-1/2
                  w-10 h-10 bg-white rounded-full shadow place-content-center">
        ›
      </button>
        </div>
      </div>

      {/* ── calendar ────────────────────────────────────────────── */}
<main className="relative flex-1 min-h-0 px-4 md:px-10 pb-4">        <FullCalendar
          ref={calRef}
          plugins={[dayGridPlugin, timeGridPlugin, interactionPlugin]}
          initialView="timeGridWeek"
          headerToolbar={false}
          height="100%"
          eventDisplay="block"
          events={events as EventInput[]}
          dateClick={(arg: DateClickArg) => openCreate(arg.dateStr)}
          eventClick={(arg: EventClickArg) => {
            const e = events.find((x) => x.id === arg.event.id);
            if (e) openEdit({ ...e, id: +e.id });
          }}
        />
      </main>

      {/* ── modal ──────────────────────────────────────────────── */}
      {modalInit !== null && (
        <EventModal
          initial={modalInit ?? undefined}
          onClose={() => setModalInit(null)}
          onSaved={handleSaved}
        />
      )}

      <NewEventModal
        open={showNew}
        onClose={() => setShowNew(false)}
        onSubmit={handleNewSubmit}
      />
    </div>
  );
}