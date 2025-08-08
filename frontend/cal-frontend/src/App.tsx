import { useEffect, useRef, useState } from "react";
import FullCalendar from "@fullcalendar/react";
import dayGridPlugin from "@fullcalendar/daygrid";
import timeGridPlugin from "@fullcalendar/timegrid";
import interactionPlugin from "@fullcalendar/interaction";
import type { DateClickArg } from "@fullcalendar/interaction";
import type { EventClickArg, EventInput } from "@fullcalendar/core";

import { listEvents } from "./api";
import type { EventOut as ApiEvent, EventIn } from "./api";
import EventModal from "./EventModal";
import NewEventModal from "./NewEventModal";

import "./index.css";
import "./App.css";

type CalEvent = Omit<ApiEvent, "id"> & { id: string };

const HEADER_H = 64;   // h-16
const TOOLBAR_H = 48;  // h-12
const EXTRA_PAD = 16;  // breathing room

export default function App() {
  const [events, setEvents] = useState<CalEvent[]>([]);
  const [modalInit, setModalInit] = useState<ApiEvent | undefined | null>(null);
  const [showNew, setShowNew] = useState(false);
  const [vh, setVh] = useState<number>(typeof window !== "undefined" ? window.innerHeight : 800);
  const calRef = useRef<FullCalendar | null>(null);

  const gotoDate  = (iso: string) => calRef.current?.getApi().gotoDate(iso);
  const gotoPrev  = () => calRef.current?.getApi().prev();
  const gotoNext  = () => calRef.current?.getApi().next();

  const reload = () =>
    listEvents()
      .then((api) => setEvents(api.map((e) => ({ ...e, id: e.id.toString() }))))
      .catch(console.error);

  useEffect(() => {
    reload().then(() => {
      const last = events.at(-1);
      if (last) gotoDate(last.start);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const onResize = () => {
      setVh(window.innerHeight);
      calRef.current?.getApi().updateSize();
    };
    setTimeout(onResize, 0);
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  const openCreate = (dateISO?: string) =>
    setModalInit(
      dateISO
        ? { id: 0, title: "", start: dateISO + "T00:00", end: dateISO + "T01:00" }
        : undefined,
    );

  const openEdit = (evt: ApiEvent) => setModalInit(evt);

  const handleSaved = (e?: ApiEvent) => {
    if (e) gotoDate(e.start);
    reload();
    setModalInit(null);
  };

  const handleNewSubmit = (p: Partial<EventIn> & { thumb?: string; repeatDays?: number[]; repeatUntil?: string }) => {
    const now = new Date();
    const defStart = new Date(now); defStart.setMinutes(0,0,0);
    const defEnd   = new Date(defStart); defEnd.setHours(defStart.getHours() + 1);

    const initial: ApiEvent = {
      id: 0,
      title: p.title ?? "",
      start: p.start ?? defStart.toISOString().slice(0,19),
      end:   p.end   ?? defEnd.toISOString().slice(0,19),
    } as any;

    (initial as any).thumb = p.thumb;
    (initial as any).repeatDays = p.repeatDays;
    (initial as any).repeatUntil = p.repeatUntil;

    setModalInit(initial);
    setShowNew(false);
  };

  const CAL_HEIGHT = Math.max(320, vh - HEADER_H - TOOLBAR_H - EXTRA_PAD);

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
      <div className="app-shell flex min-h-screen flex-col w-full">
        <header className="h-16 relative flex items-center justify-center bg-white shadow">
          <button
            onClick={() => setShowNew(true)}
            className="absolute left-6 bg-black text-white px-3 py-1 rounded"
          >
            + New
          </button>
          <h1 className="text-xl font-semibold select-none">Cal</h1>
        </header>

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
              className="hidden md:grid fixed left-2 top-1/2 -translate-y-1/2 w-10 h-10 bg-white rounded-full shadow place-content-center"
            >
              ‹
            </button>
            <button
              onClick={gotoNext}
              className="hidden md:grid fixed right-2 top-1/2 -translate-y-1/2 w-10 h-10 bg-white rounded-full shadow place-content-center"
            >
              ›
            </button>
          </div>
        </div>

        <main className="relative flex-1 min-h-0 px-0 md:px-0 pb-4">
          <FullCalendar
            ref={calRef}
            plugins={[dayGridPlugin, timeGridPlugin, interactionPlugin]}
            initialView="timeGridWeek"
            headerToolbar={false}
            timeZone="local"                 // <-- make rendering explicitly local
            height={CAL_HEIGHT}
            eventDisplay="block"
            events={events as EventInput[]}
            dateClick={(arg: DateClickArg) => openCreate(arg.dateStr)}
            eventClick={(arg: EventClickArg) => {
              const e = events.find((x) => x.id === arg.event.id);
              if (e) openEdit({ ...e, id: +e.id });
            }}
          />
        </main>
      </div>

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