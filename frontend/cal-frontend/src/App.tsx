import { useEffect, useRef, useState } from "react";
import FullCalendar from "@fullcalendar/react";
import dayGridPlugin from "@fullcalendar/daygrid";
import timeGridPlugin from "@fullcalendar/timegrid";
import interactionPlugin from "@fullcalendar/interaction";
import type { DateClickArg, EventResizeDoneArg } from "@fullcalendar/interaction";

import type {
  EventDropArg,
  EventClickArg,
  EventInput,
  EventContentArg,
} from "@fullcalendar/core";
import { listEvents, updateEvent, suggestNext, BASE_URL } from "./api";
import type { EventOut as ApiEvent, EventIn } from "./api";
import EventModal from "./EventModal";
import NewEventModal from "./NewEventModal";

import "./index.css";
import "./App.css";

type CalEvent = Omit<ApiEvent, "id"> & { id: string };

const HEADER_H = 64;   // h-16
const TOOLBAR_H = 48;  // h-12
const EXTRA_PAD = 16;  // breathing room

const LS_VIEW = "cal:view";
const LS_DATE = "cal:date";

export default function App() {
  const [events, setEvents] = useState<CalEvent[]>([]);
  const [modalInit, setModalInit] = useState<ApiEvent | undefined | null>(null);
  const [showNew, setShowNew] = useState(false);
  const [vh, setVh] = useState<number>(typeof window !== "undefined" ? window.innerHeight : 800);
  const calRef = useRef<FullCalendar | null>(null);

  const gotoDate  = (iso: string) => calRef.current?.getApi().gotoDate(iso);
  const gotoPrev  = () => calRef.current?.getApi().prev();
  const gotoNext  = () => calRef.current?.getApi().next();
  const gotoToday = () => calRef.current?.getApi().today();

  // range-aware reload (safe if backend ignores params)
  const reload = (start?: string, end?: string) =>
    listEvents(start, end)
      .then((api) => {
        const evs = api.map((e) => ({ ...e, id: e.id.toString() }));
        setEvents(evs);
        return evs;
      })
      .catch((e) => { console.error(e); return []; });

  

  // initial load + restore view/date
  useEffect(() => {
    reload().then((loaded) => {
      const api = calRef.current?.getApi();
      const savedView = localStorage.getItem(LS_VIEW) as any;
      const savedDate = localStorage.getItem(LS_DATE) as any;
      if (api) {
        if (savedView) api.changeView(savedView);
        if (savedDate) api.gotoDate(savedDate);
        else if (loaded.length) api.gotoDate(loaded[loaded.length - 1]!.start);

      }
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // height recompute on resize
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

  const handleSaved = (e: ApiEvent | undefined, _mode?: "create"|"update"|"delete") => {
    if (e) gotoDate(e.start);
    reload();
    setModalInit(null);
  };

  const handleNewSubmit = (
    p: Partial<EventIn> & {
      thumb?: string;
      repeatDays?: number[];
      repeatUntil?: string;        // YYYY-MM-DD (local)
      repeatEveryWeeks?: number;   // e.g., 2 for biweekly
    }
  ) => {
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
    (initial as any).repeatEveryWeeks = p.repeatEveryWeeks;

    setModalInit(initial);
    setShowNew(false);
  };

  const CAL_HEIGHT = Math.max(320, vh - HEADER_H - TOOLBAR_H - EXTRA_PAD);

  // ---------- ICS export for visible range ----------
  const exportICS = () => {
    const api = calRef.current?.getApi();
    if (!api) return;
    const start = api.view.activeStart.toISOString();
    const end   = api.view.activeEnd.toISOString();
    const url = `${BASE_URL}/events.ics?start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}`;
    window.open(url, "_blank");
  };

  // ---------- Drag/drop + resize handlers ----------
  const buildPayloadFromEvent = (fc: any): EventIn => {
    // fc is FullCalendar's EventApi
    const ext = fc.extendedProps || {};
    // Important: toISOString() -> UTC ISO (backend expects that)
    const startIso = fc.start ? fc.start.toISOString() : new Date().toISOString();
    const endIso   = fc.end   ? fc.end.toISOString()   : new Date(fc.start.getTime()+60*60*1000).toISOString();
    return {
      title: fc.title,
      start: startIso,
      end:   endIso,
      // include optional fields if present
      description: typeof ext.description === "string" ? ext.description : undefined,
      location:    typeof ext.location === "string" ? ext.location : undefined,
    };
  };

  async function applyUpdateOrSuggest(fcEvent: any, revert: () => void) {
    const id = Number(fcEvent.id);
    const payload = buildPayloadFromEvent(fcEvent);

    try {
      await updateEvent(id, payload);
      reload(); // reflect changes
    } catch (err: any) {
      // try suggestion on conflict
      if (err?.response?.status === 409) {
        try {
          const s = await suggestNext(payload.start, payload.end);
          const ok = window.confirm(
            `That time conflicts. Use next free slot?\n\n` +
            `${new Date(s.start).toLocaleString()} – ${new Date(s.end).toLocaleTimeString()}`);
          if (ok) {
            // move the dragged/resized event visually, then save again
            fcEvent.setStart(new Date(s.start));
            fcEvent.setEnd(new Date(s.end));
            await updateEvent(id, buildPayloadFromEvent(fcEvent));
            reload();
            return;
          }
        } catch {
          /* ignore suggest errors; we’ll revert */
        }
      }
      // anything else → revert
      revert();
    }
  }

  const onEventDrop = async (arg: EventDropArg) => {
    await applyUpdateOrSuggest(arg.event, arg.revert);
  };

  const onEventResize = async (arg: EventResizeDoneArg) => {
    await applyUpdateOrSuggest(arg.event, arg.revert);
  };

  // Nice compact event rendering: title + (location)
  const renderEvent = (arg: EventContentArg) => {
    const loc = arg.event.extendedProps?.location as string | undefined;
    const root = document.createElement("div");
    const title = document.createElement("div");
    title.textContent = arg.event.title || "(untitled)";
    title.style.fontWeight = "600";
    title.style.fontSize = "0.82rem";
    root.appendChild(title);

    if (loc) {
      const el = document.createElement("div");
      el.textContent = loc;
      el.style.fontSize = "0.72rem";
      el.style.opacity = "0.8";
      root.appendChild(el);
    }
    return { domNodes: [root] };
  };

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

          <button
            onClick={exportICS}
            className="absolute right-6 px-3 py-1 rounded border"
            title="Export current view to ICS"
          >
            Export ICS
          </button>
        </header>

        <div className="h-12 flex items-center justify-between px-4 md:px-8 bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700">
          <div className="space-x-1 text-sm">
            <button onClick={gotoToday} className="px-2 py-1 rounded hover:bg-gray-100 dark:hover:bg-gray-700">Today</button>
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
            timeZone="local"
            height={CAL_HEIGHT}
            eventDisplay="block"
            events={events as EventInput[]}
            editable={true}                // ← enable drag & resize
            eventDrop={onEventDrop}
            eventResize={onEventResize}
            eventContent={renderEvent}
            eventDidMount={(info) => {
              // Simple tooltip using title attribute with description if present
              const desc = info.event.extendedProps?.description as string | undefined;
              const loc  = info.event.extendedProps?.location as string | undefined;
              const bits = [loc, desc].filter(Boolean);
              if (bits.length) info.el.title = bits.join("\n\n");
            }}
            dateClick={(arg: DateClickArg) => openCreate(arg.dateStr)}
            eventClick={(arg: EventClickArg) => {
              const e = events.find((x) => x.id === arg.event.id);
              if (e) openEdit({ ...e, id: +e.id });
            }}
            datesSet={(arg) => {
              // persist current view & anchor date
              localStorage.setItem(LS_VIEW, arg.view.type);
              const current = calRef.current?.getApi().getDate();
              if (current) localStorage.setItem(LS_DATE, current.toISOString());
              // fetch only visible range (safe if backend ignores)
              const startStr = arg.startStr; // ISO
              const endStr   = arg.endStr;   // ISO (exclusive)
              reload(startStr, endStr);
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