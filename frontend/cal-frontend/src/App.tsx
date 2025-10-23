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
import NewEventModal from "./NewEventModal";

import "./index.css";
import "./App.css";

type CalEvent = Omit<ApiEvent, "id"> & { id: string };

const LS_VIEW = "cal:view";
const LS_DATE = "cal:date";

// Custom DOW labels to match your artwork (TUES., THUR., etc.)
const DOW_FMT = ["SUN.", "MON.", "TUES.", "WED.", "THUR.", "FRI.", "SAT."] as const;

function headerLabel(date: Date, viewType: string) {
  const dow = DOW_FMT[date.getDay()];
  if (viewType === "dayGridMonth") {
    return dow; // e.g., SUN.
  }
  const mm = String(date.getMonth() + 1).padStart(2, "0");
  const dd = String(date.getDate()).padStart(2, "0");
  return `${dow} ${mm}/${dd}`; // e.g., WED. 02/26
}

// SVG arrow — slightly larger glyph to match mock
function ArrowSVG({ dir }: { dir: "left" | "right" }) {
  const transform = dir === "left" ? "scale(-1,1) translate(-56,0)" : undefined;
  return (
    <svg width="56" height="56" viewBox="0 0 56 56" aria-hidden focusable="false" className="v-arrow">
      <g transform={transform}>
        <rect x="10" y="24" width="28" height="8" rx="4" />
        <path d="M36 12 L50 28 L36 44 Z" />
      </g>
    </svg>
  );
}

export default function App() {
  const [events, setEvents] = useState<CalEvent[]>([]);
  const [modalInit, setModalInit] = useState<ApiEvent | undefined | null>(null);
  const [showNew, setShowNew] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [layout, setLayout] = useState<'attached'|'floating'>(
    (localStorage.getItem('cal:layout') as 'attached'|'floating') || 'attached'
  );
  const [viewType, setViewType] = useState<string>('timeGridWeek');

  const calRef = useRef<FullCalendar | null>(null);
  const toolsRef = useRef<HTMLDivElement | null>(null);

  // anchor date for large header (Month + Year)
  const [anchor, setAnchor] = useState<Date>(new Date());
  const monthName = anchor.toLocaleString("en-US", { month: "long" }).toUpperCase();
  const year = anchor.getFullYear();

  const gotoDate = (iso: string) => calRef.current?.getApi().gotoDate(iso);
  const gotoPrev = () => calRef.current?.getApi().prev();
  const gotoNext = () => calRef.current?.getApi().next();

  // range-aware reload
  const reload = (start?: string, end?: string) =>
    listEvents(start, end)
      .then((api) => {
        const evs = api.map((e) => ({ ...e, id: e.id.toString() }));
        setEvents(evs);
        return evs;
      })
      .catch((e) => {
        console.error(e);
        return [];
      });

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

  // ask FullCalendar to recompute sizes on window resize
  useEffect(() => {
    const onResize = () => calRef.current?.getApi().updateSize();
    setTimeout(onResize, 0);
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  // close dropdown when clicking outside
  useEffect(() => {
    const onDoc = (e: MouseEvent) => {
      if (!toolsRef.current?.contains(e.target as Node)) setMenuOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  const openCreate = (dateISO?: string) =>
    setModalInit(
      dateISO
        ? { id: 0, title: "", start: dateISO + "T00:00", end: dateISO + "T01:00" }
        : undefined
    );

  const openEdit = (evt: ApiEvent) => setModalInit(evt);

  const handleSaved = (e: ApiEvent | undefined, _mode?: "create" | "update" | "delete") => {
    if (e) gotoDate(e.start);
    reload();
    setModalInit(null);
  };

  // ---------- ICS export for visible range (kept for future use) ----------
  const exportICS = () => {
    const api = calRef.current?.getApi();
    if (!api) return;
    const start = api.view.activeStart.toISOString();
    const end = api.view.activeEnd.toISOString();
    const url = `${BASE_URL}/events.ics?start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}`;
    window.open(url, "_blank");
  };

  // ---------- Drag/drop + resize handlers ----------
  const buildPayloadFromEvent = (fc: any): EventIn => {
    const ext = fc.extendedProps || {};
    const startIso = fc.start ? fc.start.toISOString() : new Date().toISOString();
    const endIso =
      fc.end ? fc.end.toISOString() : new Date(fc.start.getTime() + 60 * 60 * 1000).toISOString();
    return {
      title: fc.title,
      start: startIso,
      end: endIso,
      description: typeof ext.description === "string" ? ext.description : undefined,
      location: typeof ext.location === "string" ? ext.location : undefined,
    };
  };

  async function applyUpdateOrSuggest(fcEvent: any, revert: () => void) {
    const id = Number(fcEvent.id);
    const payload = buildPayloadFromEvent(fcEvent);

    try {
      await updateEvent(id, payload);
      reload(); // reflect changes
    } catch (_err: any) {
      revert(); // on conflict just revert — advanced "suggest next" lives in modal flow
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
      {/* OUTER PAPER */}
      <div className="v-paper">
        {/* Left/Right arrows — unchanged */}
        <button className="v-nav v-nav-left" onClick={gotoPrev} aria-label="Previous period">
          <ArrowSVG dir="left" />
        </button>
        <button className="v-nav v-nav-right" onClick={gotoNext} aria-label="Next period">
          <ArrowSVG dir="right" />
        </button>

        {/* Top-left toolbox button */}
        <div ref={toolsRef} className="v-tools">
          <button
            type="button"
            className="v-toolbtn"
            aria-label="Calendar tools"
            onClick={() => setMenuOpen((v) => !v)}
          >
            {/* toolbox icon */}
            <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden>
              <rect x="3" y="8" width="18" height="10" rx="2" />
              <path
                d="M8 8V6a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
              />
              <rect x="7" y="11" width="10" height="3" rx="1" fill="currentColor" />
            </svg>
          </button>
          {menuOpen && (
            <div className="v-menu">
              <button
                className="v-menu-item"
                onClick={() => {
                  calRef.current?.getApi().today();
                  setMenuOpen(false);
                }}
              >
                Today
              </button>
              <button
                className="v-menu-item"
                onClick={() => {
                  calRef.current?.getApi().changeView("timeGridDay");
                  setMenuOpen(false);
                }}
              >
                Day
              </button>
              <button
                className="v-menu-item"
                onClick={() => {
                  calRef.current?.getApi().changeView("timeGridWeek");
                  setMenuOpen(false);
                }}
              >
                Week
              </button>
              <button
                className="v-menu-item"
                onClick={() => {
                  calRef.current?.getApi().changeView("dayGridMonth");
                  setMenuOpen(false);
                }}
              >
                Month
              </button>
              <button
                className="v-menu-item"
                onClick={() => {
                  setMenuOpen(false);
                  setShowNew(true);
                }}
              >
                + New
              </button>
            {/* ---- View attachment mode ---- */}
              <button
                className="v-menu-item"
                onClick={() => {
                  setLayout('floating');
                  localStorage.setItem('cal:layout','floating');
                  setMenuOpen(false);
                  setTimeout(() => calRef.current?.getApi().updateSize(), 0);
                }}
              >
                Floating
              </button>
              <button
                className="v-menu-item"
                onClick={() => {
                  setLayout('attached');
                  localStorage.setItem('cal:layout','attached');
                  setMenuOpen(false);
                  setTimeout(() => calRef.current?.getApi().updateSize(), 0);
                }}
              >
                Attached
              </button>

            </div>
          )}
        </div>

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
        <main className="relative flex-1 min-h-0 px-0 pb-0">
          <div className={`v-grid ${layout} ${viewType === 'dayGridMonth' ? 'is-month' : 'is-week'}`}>
                      <FullCalendar

            ref={calRef}
            plugins={[dayGridPlugin, timeGridPlugin, interactionPlugin]}
            initialView="timeGridWeek"
            headerToolbar={false}
            allDaySlot={false}
            slotDuration="01:00:00"
            slotLabelInterval="01:00"
            timeZone="local"
            /* 👇 fill the grid row completely — removes bottom blank space */
            height="100%"
            eventDisplay="block"
            events={events as EventInput[]}
            editable={true}
            eventDrop={onEventDrop}
            eventResize={onEventResize}
            eventContent={renderEvent}
            eventDidMount={(info) => {
              const desc = info.event.extendedProps?.description as string | undefined;
              const loc = info.event.extendedProps?.location as string | undefined;
              const bits = [loc, desc].filter(Boolean);
              if (bits.length) info.el.title = bits.join("\n\n");
            }}
            scrollTime="00:00:00"
            slotMinTime="00:00:00"
            slotMaxTime="24:00:00"
            slotLabelFormat={[{ hour: "numeric", meridiem: "short" }]}
            dayHeaderContent={(args) => headerLabel(args.date, args.view.type)}
            firstDay={0} // Sunday
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
                setAnchor(current); // keep header in sync
              }
              setViewType(arg.view.type);
              const startStr = arg.startStr;
              const endStr = arg.endStr;
              reload(startStr, endStr);
            }}
          />
          </div>
        </main>
      </div>

      {modalInit !== null && (
        <EventModal
          initial={modalInit ?? undefined}
          onClose={() => setModalInit(null)}
          onSaved={handleSaved}
        />
      )}

      {/* New → parse (text/image) → hand off to EventModal */}
      <NewEventModal
        open={showNew}
        onClose={() => setShowNew(false)}
        onSubmit={(p) => {
          setShowNew(false);
          const start = p.start ?? new Date().toISOString();
          const end = p.end ?? new Date(Date.now() + 60 * 60 * 1000).toISOString();
          setModalInit({
            id: 0,
            title: p.title ?? "",
            start,
            end,
            // @ts-ignore extras for EventModal helper features
            thumb: p.thumb,
            // @ts-ignore
            repeatDays: p.repeatDays,
            // @ts-ignore
            repeatUntil: p.repeatUntil,
            // @ts-ignore
            repeatEveryWeeks: p.repeatEveryWeeks,
          } as any);
        }}
      />
    </>
  );
}