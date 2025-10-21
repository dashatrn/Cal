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
import { listEvents, updateEvent, BASE_URL } from "./api";
import type { EventOut as ApiEvent, EventIn } from "./api";
import EventModal from "./EventModal";

import "./index.css";
import "./App.css";

type CalEvent = Omit<ApiEvent, "id"> & { id: string };

const HEADER_H = 220;  // approximate header height (plaque + monthbar)
const TOOLBAR_H = 0;   // we removed internal toolbar
const EXTRA_PAD = 16;

const LS_VIEW = "cal:view";
const LS_DATE = "cal:date";

// Custom DOW labels to match your artwork (TUES., THUR., etc.)
const DOW_FMT = ["SUN.","MON.","TUES.","WED.","THUR.","FRI.","SAT."] as const;

function headerLabel(date: Date, viewType: string) {
  const dow = DOW_FMT[date.getDay()];
  if (viewType === "dayGridMonth") {
    return dow;                         // e.g., SUN.
  }
  const mm = String(date.getMonth() + 1).padStart(2, "0");
  const dd = String(date.getDate()).padStart(2, "0");
  return `${dow} ${mm}/${dd}`;          // e.g., WED. 02/26
}

// SVG arrow that matches the mock (solid red arrow inside a round beige button)
function ArrowSVG({ dir }: { dir: "left" | "right" }) {
  const transform = dir === "left" ? "scale(-1,1) translate(-56,0)" : undefined;
  return (
    <svg width="32" height="32" viewBox="0 0 56 56" aria-hidden focusable="false" className="v-arrow">
      <g transform={transform}>
        {/* shaft */}
        <rect x="12" y="25" width="24" height="6" rx="3" />
        {/* head */}
        <path d="M34 14 L48 28 L34 42 Z" />
      </g>
    </svg>
  );
}

export default function App() {
  const [events, setEvents] = useState<CalEvent[]>([]);
  const [modalInit, setModalInit] = useState<ApiEvent | undefined | null>(null);
  const [vh, setVh] = useState<number>(typeof window !== "undefined" ? window.innerHeight : 800);
  const calRef = useRef<FullCalendar | null>(null);

  // anchor date for large header (Month + Year)
  const [anchor, setAnchor] = useState<Date>(new Date());
  const monthName = anchor.toLocaleString("en-US", { month: "long" }).toUpperCase();
  const year = anchor.getFullYear();

  const gotoDate  = (iso: string) => calRef.current?.getApi().gotoDate(iso);
  const gotoPrev  = () => calRef.current?.getApi().prev();
  const gotoNext  = () => calRef.current?.getApi().next();

  // range-aware reload
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
      const current = api?.getDate();
      if (current) setAnchor(current);
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

  const CAL_HEIGHT = Math.max(320, vh - HEADER_H - TOOLBAR_H - EXTRA_PAD);

  // ---------- ICS export for visible range (kept for future use) ----------
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
    const ext = fc.extendedProps || {};
    const startIso = fc.start ? fc.start.toISOString() : new Date().toISOString();
    const endIso   = fc.end   ? fc.end.toISOString()   : new Date(fc.start.getTime()+60*60*1000).toISOString();
    return {
      title: fc.title,
      start: startIso,
      end:   endIso,
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
      // on conflict just revert — advanced "suggest next" lives in modal flow
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
    <>
      {/* Left/Right arrows floating outside paper */}
      <button className="v-nav v-nav-left" onClick={gotoPrev} aria-label="Previous week">
        <ArrowSVG dir="left" />
      </button>
      <button className="v-nav v-nav-right" onClick={gotoNext} aria-label="Next week">
        <ArrowSVG dir="right" />
      </button>

      {/* OUTER PAPER */}
      <div className="v-paper">
        {/* Plaque with “Cal” */}
        <div className="v-plaque">
          <div className="v-cal-logo">Cal</div>
        </div>

        {/* Month title row */}
        <div className="v-monthbar">
          <div className="v-year">{year}</div>
          <div className="v-month">{monthName}</div>
          <div className="v-year">{year}</div>
        </div>

        {/* Calendar */}
        <main className="relative flex-1 min-h-0 px-0 pb-4">
          <FullCalendar
            ref={calRef}
            plugins={[dayGridPlugin, timeGridPlugin, interactionPlugin]}
            initialView="timeGridWeek"
            headerToolbar={false}
            allDaySlot={false}            // ← remove ALL-DAY row to match mock
            slotDuration="01:00:00"       // ← hourly rows (no dotted half-hours)
            slotLabelInterval="01:00"     // ← show one label per hour
            timeZone="local"
            height={CAL_HEIGHT}
            eventDisplay="block"
            events={events as EventInput[]}
            editable={true}
            eventDrop={onEventDrop}
            eventResize={onEventResize}
            eventContent={renderEvent}
            eventDidMount={(info) => {
              const desc = info.event.extendedProps?.description as string | undefined;
              const loc  = info.event.extendedProps?.location as string | undefined;
              const bits = [loc, desc].filter(Boolean);
              if (bits.length) info.el.title = bits.join("\n\n");
            }}

            /* ——— The three lines below produce your desired time axis ——— */
            scrollTime="00:00:00"       // don’t auto-scroll to 6am
            slotMinTime="00:00:00"      // show hours starting at midnight
            slotMaxTime="24:00:00"      // show full day

            /* Label format like “12AM, 1AM, …” (no minutes) */
            slotLabelFormat={[{ hour: "numeric", meridiem: "short" }]}

            /* Day headers to match mockups (SUN. 02/23 etc.) */
            dayHeaderContent={(args) => headerLabel(args.date, args.view.type)}
            firstDay={0}  // Sunday
            dateClick={(arg: DateClickArg) => openCreate(arg.dateStr)}
            eventClick={(arg: EventClickArg) => {
              const e = events.find((x) => x.id === arg.event.id);
              if (e) openEdit({ ...e, id: +e.id });
            }}
            datesSet={(arg) => {
              localStorage.setItem(LS_VIEW, arg.view.type);
              const current = calRef.current?.getApi().getDate();
              if (current) {
                localStorage.setItem(LS_DATE, current.toISOString());
                setAnchor(current);     // keep header in sync
              }
              const startStr = arg.startStr;
              const endStr   = arg.endStr;
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
    </>
  );
}