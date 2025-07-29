import { useEffect, useState, useRef } from "react";
import FullCalendar from "@fullcalendar/react";
import dayGridPlugin from "@fullcalendar/daygrid";
import timeGridPlugin from "@fullcalendar/timegrid";
import interactionPlugin from "@fullcalendar/interaction";
import type { DateClickArg } from "@fullcalendar/interaction";
import type { EventClickArg, EventInput } from "@fullcalendar/core";

import { listEvents } from "./api";
import type { EventOut as ApiEvent } from "./api";
import EventModal from "./EventModal";
import "./App.css";

type CalEvent = Omit<ApiEvent, "id"> & { id: string };

export default function App() {
  const [events, setEvents] = useState<CalEvent[]>([]);
  const [modalInit, setModalInit] = useState<ApiEvent | undefined | null>(null);
  const calRef = useRef<FullCalendar | null>(null);

  /** pull everything once */
  const reload = () =>
    listEvents()
      .then((api) => setEvents(api.map((e) => ({ ...e, id: e.id.toString() }))))
      .catch(console.error);

  useEffect(() => { void reload(); }, []);
  /** helpers */
  const gotoPrev = () => calRef.current?.getApi().prev();
  const gotoNext = () => calRef.current?.getApi().next();

  const openCreate = (dateISO?: string) =>
    setModalInit(
      dateISO
        ? { id: 0, title: "", start: dateISO + "T00:00", end: dateISO + "T01:00" }
        : undefined
    );
  const openEdit = (evt: ApiEvent) => setModalInit(evt);

  /** after a modal saves, make sure state = DB truth */
  const handleSaved = () => {
    reload();                 // <—— guarantees UI matches DB
    setModalInit(null);
  };

  return (
    <div className="min-h-screen flex flex-col bg-gray-100">
      {/* header */}
      <header className="py-6 bg-white shadow flex justify-between px-6">
        <h1 className="text-3xl font-bold select-none">Cal</h1>
        <button
          type="button"
          onClick={() => openCreate()}
          className="bg-black text-white px-3 py-1 rounded"
        >
          + New
        </button>
      </header>

      {/* calendar */}
      <main className="relative flex-1 px-4 md:px-10 pb-4">
        <button onClick={gotoPrev} className="hidden md:flex absolute left-0 top-1/2 -translate-y-1/2 w-10 h-10 bg-white rounded-full shadow place-content-center">‹</button>
        <button onClick={gotoNext} className="hidden md:flex absolute right-0 top-1/2 -translate-y-1/2 w-10 h-10 bg-white rounded-full shadow place-content-center">›</button>

        <FullCalendar
          ref={calRef}
          plugins={[dayGridPlugin, timeGridPlugin, interactionPlugin]}
          /** <-- new default */
          initialView="timeGridWeek"
          events={events as EventInput[]}
          height="100%"
          headerToolbar={false}
          dateClick={(arg: DateClickArg) => openCreate(arg.dateStr)}
          eventClick={(arg: EventClickArg) => {
            const e = events.find((x) => x.id === arg.event.id);
            if (e) openEdit({ ...e, id: +e.id });
          }}
        />
      </main>

      {modalInit !== null && (
        <EventModal
          initial={modalInit ?? undefined}
          onClose={() => setModalInit(null)}
          onSaved={handleSaved}
        />
      )}
    </div>
  );
}