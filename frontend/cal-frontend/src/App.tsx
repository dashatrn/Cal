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

import YearView from "./YearView"; // ⬅️ NEW

import "./index.css";
import "./App.css";

type CalEvent = Omit<ApiEvent, "id"> & { id: string };

const LS_VIEW  = "cal:view";
const LS_DATE  = "cal:date";
const LS_FRAME = "cal:frame-mode";
const LS_YEAR  = "cal:year-mode"; // "1" when Year stub is active

type FrameMode = "attached" | "floating";

// Custom DOW labels to match artwork (TUES., THUR., etc.)
const DOW_FMT = ["SUN.", "MON.", "TUES.", "WED.", "THUR.", "FRI.", "SAT."] as const;

function headerLabel(date: Date, viewType: string) {
  const dow = DOW_FMT[date.getDay()];
  if (viewType === "dayGridMonth") return dow;
  const mm = String(date.getMonth() + 1).padStart(2, "0");
  const dd = String(date.getDate()).padStart(2, "0");
  return `${dow} ${mm}/${dd}`;
}

// SVG arrow
function ArrowSVG({ dir }: { dir: "left" | "right" }) {
  const transform = dir === "left" ? "scale(-1,1) translate(-56,0)" : undefined;
  return (
    <svg width="44" height="44" viewBox="0 0 56 56" aria-hidden focusable="false" className="v-arrow">
      <g transform={transform}>
        <rect x="10" y="24" width="28" height="8" rx="4" />
        <path d="M36 12 L50 28 L36 44 Z" />
      </g>
    </svg>
  );
}

// Placeholder mini calendar icon
function MiniCalIcon() {
  return (
    <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden>
      <rect x="3" y="5" width="18" height="14" rx="2" fill="currentColor" opacity="0.12" />
      <rect x="3" y="7" width="18" height="12" rx="2" stroke="currentColor" strokeWidth="2" fill="none" />
      <rect x="6" y="3" width="3" height="4" rx="1" fill="currentColor" />
      <rect x="15" y="3" width="3" height="4" rx="1" fill="currentColor" />
      {/* grid */}
      <path d="M6 11H18M6 14H18M6 17H18M9 9V19M12 9V19M15 9V19" stroke="currentColor" strokeWidth="1" />
    </svg>
  );
}

// Toolbox/briefcase icon
function ToolboxIcon() {
  return (
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
  );
}

export default function App() {
  const [events, setEvents] = useState<CalEvent[]>([]);
  const [modalInit, setModalInit] = useState<ApiEvent | undefined | null>(null);
  const [showNew, setShowNew] = useState(false);

  // Two separate menus (calendar vs toolbox)
  const [menuCalOpen, setMenuCalOpen] = useState(false);
  const [menuToolsOpen, setMenuToolsOpen] = useState(false);

  const calRef = useRef<FullCalendar | null>(null);
  const toolsRef = useRef<HTMLDivElement | null>(null);

  // anchor date for big header
  const [anchor, setAnchor] = useState<Date>(new Date());
  const monthName = anchor.toLocaleString("en-US", { month: "long" }).toUpperCase();
  const year = anchor.getFullYear();

  // current FC view type for styling
  const [viewType, setViewType] = useState<string>("timeGridWeek");

  // TRUE = show our custom YearView instead of FC month
  const [yearMode, setYearMode] = useState<boolean>(() => {
    return typeof window !== "undefined" && localStorage.getItem(LS_YEAR) === "1";
  });
  const yearModeRef = useRef<boolean>(yearMode);
  useEffect(() => { yearModeRef.current = yearMode; }, [yearMode]);

  // frame mode (attached vs floating)
  const [frameMode, setFrameMode] = useState<FrameMode>(() => {
    const saved = (typeof window !== "undefined" && localStorage.getItem(LS_FRAME)) as FrameMode | null;
    return saved === "floating" ? "floating" : "attached";
  });

  // Request YearView to scroll to a specific month when arrows are used
  const [yearJump, setYearJump] = useState<Date | undefined>(undefined);

  const gotoDate = (iso: string) => calRef.current?.getApi().gotoDate(iso);

  const gotoPrev = () => {
    if (yearModeRef.current) {
      const prev = new Date(anchor.getFullYear(), anchor.getMonth() - 1, 1);
      setYearJump(prev);
      setAnchor(prev);
    } else {
      calRef.current?.getApi().prev();
    }
  };
  const gotoNext = () => {
    if (yearModeRef.current) {
      const next = new Date(anchor.getFullYear(), anchor.getMonth() + 1, 1);
      setYearJump(next);
      setAnchor(next);
    } else {
      calRef.current?.getApi().next();
    }
  };

  // reload events for a range
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

  // initial load + restore view/date/year mode
  useEffect(() => {
    reload().then((loaded) => {
      const api = calRef.current?.getApi();
      const savedView = localStorage.getItem(LS_VIEW) as any;
      const savedDate = localStorage.getItem(LS_DATE) as any;
      if (api) {
        if (savedView && !yearModeRef.current) api.changeView(savedView);
        if (savedDate && !yearModeRef.current) api.gotoDate(savedDate);
        else if (loaded.length && !yearModeRef.current) api.gotoDate(loaded[loaded.length - 1]!.start);

        if (localStorage.getItem(LS_YEAR) === "1") {
          setYearMode(true);
          setViewType("year"); // tag for styling
        } else {
          setViewType(api?.view?.type || "timeGridWeek");
        }
      }
      const current = api?.getDate() || new Date();
      setAnchor(current);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // recompute sizes on resize
  useEffect(() => {
    const onResize = () => calRef.current?.getApi().updateSize();
    setTimeout(onResize, 0);
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  // close both menus when clicking outside
  useEffect(() => {
    const onDoc = (e: MouseEvent) => {
      if (!toolsRef.current?.contains(e.target as Node)) {
        setMenuCalOpen(false);
        setMenuToolsOpen(false);
      }
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

  // Export ICS for visible range (kept for future use)
  const exportICS = () => {
    const api = calRef.current?.getApi();
    if (!api) return;
    const start = api.view.activeStart.toISOString();
    const end = api.view.activeEnd.toISOString();
    const url = `${BASE_URL}/events.ics?start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}`;
    window.open(url, "_blank");
  };

  // drag/drop + resize handlers
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
      reload();
    } catch (_err: any) {
      revert();
    }
  }

  const onEventDrop = async (arg: EventDropArg) => {
    await applyUpdateOrSuggest(arg.event, arg.revert);
  };

  const onEventResize = async (arg: EventResizeDoneArg) => {
    await applyUpdateOrSuggest(arg.event, arg.revert);
  };

  // compact event renderer
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

  // classes to control floating/attached and view-specific borders
  const frameClass = frameMode === "floating" ? "is-floating" : "is-attached";
  const viewClass =
    yearMode
      ? "view-year"
      : (viewType === "dayGridMonth"
          ? "view-month"
          : viewType === "timeGridDay"
            ? "view-day"
            : "view-week");

  // -------- Mini calendar actions --------
  const goToday = () => {
    if (yearModeRef.current) {
      const now = new Date();
      setYearJump(now);
      setAnchor(now);
    } else {
      calRef.current?.getApi().today();
    }
    setMenuCalOpen(false);
  };

  const setWeek = () => {
    calRef.current?.getApi().changeView("timeGridWeek");
    setYearMode(false);
    localStorage.setItem(LS_YEAR, "0");
    setViewType("timeGridWeek");
    setMenuCalOpen(false);
  };

  const setMonth = () => {
    calRef.current?.getApi().changeView("dayGridMonth");
    setYearMode(false);
    localStorage.setItem(LS_YEAR, "0");
    setViewType("dayGridMonth");
    setMenuCalOpen(false);
  };

  const setYear = () => {
    // Real Year view now
    setYearMode(true);
    localStorage.setItem(LS_YEAR, "1");
    setViewType("year");
    setMenuCalOpen(false);
  };

  // ---------- Helpers for hover/click behaviors ----------
  function armMonthTopHover(arg: any) {
    if (arg.view?.type !== "dayGridMonth" || yearModeRef.current) return;
    const cellEl: HTMLElement = arg.el;
    const top = cellEl.querySelector<HTMLElement>(".fc-daygrid-day-top");
    if (!top) return;

    const date = arg.date;

    const enter = () => {
      cellEl.classList.add("is-hover");
      top.classList.add("hover-armed");
    };
    const leave = () => {
      cellEl.classList.remove("is-hover");
      top.classList.remove("hover-armed");
    };
    const click = () => {
      // open Day view for that date
      calRef.current?.getApi().changeView("timeGridDay", date);
    };

    top.addEventListener("mouseenter", enter);
    top.addEventListener("mouseleave", leave);
    top.addEventListener("click", click);
  }

  function armWeekHeaderHover(arg: any) {
    if (arg.view?.type !== "timeGridWeek") return;

    const th: HTMLElement = arg.el;
    const dateStr = arg.date?.toISOString?.().slice(0, 10);
    if (!dateStr) return;

    const columns = () =>
      Array.from(document.querySelectorAll<HTMLElement>(`.fc-timegrid-col[data-date="${dateStr}"]`));

    const enter = () => {
      th.classList.add("is-hover");
      columns().forEach((c) => c.classList.add("is-hover"));
    };
    const leave = () => {
      th.classList.remove("is-hover");
      columns().forEach((c) => c.classList.remove("is-hover"));
    };
    const click = () => {
      calRef.current?.getApi().changeView("timeGridDay", arg.date);
    };

    th.addEventListener("mouseenter", enter);
    th.addEventListener("mouseleave", leave);
    th.addEventListener("click", click);
  }

  return (
    <>
      {/* OUTER PAPER */}
      <div className="v-paper">
        {/* Left/Right arrows */}
        <button className="v-nav v-nav-left" onClick={gotoPrev} aria-label="Previous period">
          <ArrowSVG dir="left" />
        </button>
        <button className="v-nav v-nav-right" onClick={gotoNext} aria-label="Next period">
          <ArrowSVG dir="right" />
        </button>

        {/* Tools cluster (top-left): Mini calendar + Toolbox (stacked) */}
        <div ref={toolsRef} className="v-tools">
          <div className="v-toolwrap">
            <button
              type="button"
              className="v-toolbtn"
              aria-label="Calendar"
              onClick={() => {
                setMenuCalOpen((v) => !v);
                setMenuToolsOpen(false);
              }}
            >
              <MiniCalIcon />
            </button>
            {menuCalOpen && (
              <div className="v-menu v-menu-cal">
                <button className="v-menu-item" onClick={goToday}>Today</button>
                <button className="v-menu-item" onClick={setWeek}>Week</button>
                <button className="v-menu-item" onClick={setMonth}>Month</button>
                <button className="v-menu-item" onClick={setYear}>Year</button>
              </div>
            )}
          </div>

          <div className="v-toolwrap">
            <button
              type="button"
              className="v-toolbtn"
              aria-label="Toolbox"
              onClick={() => {
                setMenuToolsOpen((v) => !v);
                setMenuCalOpen(false);
              }}
            >
              <ToolboxIcon />
            </button>
            {menuToolsOpen && (
              <div className="v-menu v-menu-tools">
                <button
                  className="v-menu-item"
                  onClick={() => {
                    setMenuToolsOpen(false);
                    setShowNew(true);
                  }}
                >
                  + New
                </button>
                <button
                  className="v-menu-item"
                  onClick={() => {
                    setFrameMode("attached");
                    localStorage.setItem(LS_FRAME, "attached");
                    setMenuToolsOpen(false);
                  }}
                >
                  Attached
                </button>
                <button
                  className="v-menu-item"
                  onClick={() => {
                    setFrameMode("floating");
                    localStorage.setItem(LS_FRAME, "floating");
                    setMenuToolsOpen(false);
                  }}
                >
                  Floating
                </button>
              </div>
            )}
          </div>
        </div>

        {/* Plaque with “Cal” + roses */}
        <div className="v-plaque">
          <img aria-hidden src="/roses-divider2.png" className="v-rose v-rose-left" />
          <div className="v-cal-logo">Cal</div>
          <img aria-hidden src="/roses-divider.png" className="v-rose v-rose-right" />
        </div>

        {/* Month title row (compact when not in Month) */}
        <div className={`v-monthbar ${(!yearMode && viewType === "dayGridMonth") ? "" : "is-compact"}`}>
          <div className="v-year">{year}</div>
          <div className="v-month">{monthName}</div>
          <div className="v-year">{year}</div>
        </div>

        {/* Calendar */}
        <main className={`relative flex-1 min-h-0 px-0 pb-0 ${frameClass} ${viewClass}`}>
          {yearMode ? (
            <YearView
              jumpTo={yearJump}
              onAnchorChange={(d) => setAnchor(d)}
            />
          ) : (
            <FullCalendar
              ref={calRef}
              plugins={[dayGridPlugin, timeGridPlugin, interactionPlugin]}
              initialView="timeGridWeek"
              headerToolbar={false}
              allDaySlot={false}
              slotDuration="01:00:00"
              slotLabelInterval="01:00"
              timeZone="local"
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
                // persist view/date
                localStorage.setItem(LS_VIEW, arg.view.type);
                const current = calRef.current?.getApi().getDate();
                if (current) {
                  localStorage.setItem(LS_DATE, current.toISOString());
                  setAnchor(current);
                }
                // keep events in range
                reload(arg.startStr, arg.endStr);
                setViewType(arg.view.type);
              }}

              /* ✨ NEW: behaviors */
              dayCellDidMount={armMonthTopHover}
              dayHeaderDidMount={armWeekHeaderHover}
            />
          )}
        </main>
      </div>

      {modalInit !== null && (
        <EventModal
          initial={modalInit ?? undefined}
          onClose={() => setModalInit(null)}
          onSaved={handleSaved}
        />
      )}

      {/* New → parse (text/image) → EventModal */}
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