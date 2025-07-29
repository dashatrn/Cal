import { useEffect, useState, useRef } from "react";
import FullCalendar from "@fullcalendar/react";
import dayGridPlugin from "@fullcalendar/daygrid";
import interactionPlugin from "@fullcalendar/interaction";
import type { DateClickArg } from "@fullcalendar/interaction";   // ← type-only
import type { EventClickArg, EventInput } from "@fullcalendar/core";

import "./App.css";
import { listEvents } from "./api";
import type { EventOut as ApiEvent } from "./api";
import EventModal from "./EventModal";

/** Calendar-friendly shape: id must be a string */
type CalEvent = Omit<ApiEvent, "id"> & { id: string };

export default function App() {
  const [events, setEvents] = useState<CalEvent[]>([]);
  const [modalInit, setModalInit] = useState<ApiEvent | null | undefined>(null);
  const calRef = useRef<FullCalendar | null>(null);

  // ─────────────────────────────── initial load
  useEffect(() => {
    listEvents()
      .then((api) =>
        setEvents(api.map((e) => ({ ...e, id: e.id.toString() })))
      )
      .catch(console.error);
  }, []);

  // ─────────────────────────────── helpers
  const gotoPrev = () => calRef.current?.getApi().prev();
  const gotoNext = () => calRef.current?.getApi().next();

  const openCreate = () => setModalInit(undefined);          // ② NEW  const openEdit = (apiEvent: ApiEvent) => setModalInit(apiEvent);
  const openEdit = (apiEvent: ApiEvent) => setModalInit(apiEvent);
  const handleSaved = (
    evt: ApiEvent,
    mode: "create" | "update" | "delete"
  ) => {
    setEvents((curr) => {
      if (mode === "create")
        return [...curr, { ...evt, id: evt.id.toString() }];
      if (mode === "update")
        return curr.map((e) =>
          e.id === evt.id.toString() ? { ...evt, id: evt.id.toString() } : e
        );
      if (mode === "delete")
        return curr.filter((e) => e.id !== evt.id.toString());
      return curr;
    });
  };

  // ─────────────────────────────── render
  return (
    <div className="min-h-screen flex flex-col bg-gray-100">
      {/* ——— header ——— */}
      <header className="py-6 text-center bg-white shadow flex justify-between px-6">
        <h1 className="text-4xl font-extrabold tracking-wide select-none">
          C&nbsp;a&nbsp;l
        </h1>
        <button
          onClick={openCreate}
          className="bg-black text-white px-3 py-1 rounded"
        >
          + New
        </button>
      </header>

      {/* ——— calendar area ——— */}
      <main className="relative flex-1 px-4 md:px-10 pb-4">
        {/* arrows */}
        <button
          onClick={gotoPrev}
          className="hidden md:flex items-center justify-center
                     absolute left-0 top-1/2 -translate-y-1/2
                     w-10 h-10 bg-white rounded-full shadow
                     hover:bg-gray-100"
          aria-label="Previous"
        >
          ‹
        </button>
        <button
          onClick={gotoNext}
          className="hidden md:flex items-center justify-center
                     absolute right-0 top-1/2 -translate-y-1/2
                     w-10 h-10 bg-white rounded-full shadow
                     hover:bg-gray-100"
          aria-label="Next"
        >
          ›
        </button>

        {/* FullCalendar */}
        <FullCalendar
          ref={calRef}
          plugins={[dayGridPlugin, interactionPlugin]}
          initialView="dayGridWeek"
          events={events as EventInput[]}
          height="100%"
          headerToolbar={false}
          dateClick={(_: DateClickArg) => openCreate()}
          eventClick={(arg: EventClickArg) => {
            const evt = events.find((e) => e.id === arg.event.id);
            if (evt) openEdit({ ...evt, id: +evt.id });
          }}
        />
      </main>

        {/* modal */}
      {modalInit !== null && (                                   /* ③ condition */
        <EventModal
          initial={modalInit}                                    // undefined or event
          onClose={() => setModalInit(null)}
          onSaved={handleSaved}
        />
      )}
    </div>
  );

}