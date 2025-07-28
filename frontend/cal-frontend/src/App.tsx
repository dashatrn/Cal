import { useEffect, useState, useRef } from "react";
import FullCalendar from "@fullcalendar/react";
import dayGridPlugin from "@fullcalendar/daygrid";

import "./App.css";
import { listEvents } from "./api";
import type { EventOut as ApiEvent } from "./api";

/** Calendar-friendly shape: id must be a string */
type CalEvent = Omit<ApiEvent, "id"> & { id: string };

export default function App() {
  const [events, setEvents] = useState<CalEvent[]>([]);
  const calRef = useRef<FullCalendar | null>(null);

  // initial load
  useEffect(() => {
    listEvents()
      .then(apiEvents =>
        setEvents(apiEvents.map(e => ({ ...e, id: e.id.toString() })))
      )
      .catch(console.error);
  }, []);

  /** side-arrow helpers */
  const gotoPrev = () => calRef.current?.getApi().prev();
  const gotoNext = () => calRef.current?.getApi().next();

  return (
    <div className="min-h-screen flex flex-col bg-gray-100">
      {/* ——— header ——— */}
      <header className="py-6 text-center bg-white shadow">
        <h1 className="text-4xl font-extrabold tracking-wide">C&nbsp;a&nbsp;l</h1>
      </header>

      {/* ——— calendar area ——— */}
      <main className="relative flex-1 px-4 md:px-10 pb-4">
        {/* left arrow */}
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

        {/* right arrow */}
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

        {/* FullCalendar itself */}
        <FullCalendar
          ref={calRef}
          plugins={[dayGridPlugin]}
          initialView="dayGridWeek"
          events={events}
          height="100%"
          headerToolbar={false}
        />
      </main>
    </div>
  );
}