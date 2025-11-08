import { useEffect, useMemo, useRef, useState } from "react";

type Props = {
  /** Month to jump/center to (we'll ensure it's in range and scroll it into view). */
  jumpTo?: Date;
  /** Report a reasonable "anchor" month so your header (month/year) updates. */
  onAnchorChange?: (d: Date) => void;
};

function firstOfMonth(d: Date) {
  return new Date(d.getFullYear(), d.getMonth(), 1);
}
function addMonths(d: Date, n: number) {
  return new Date(d.getFullYear(), d.getMonth() + n, 1);
}
function daysInMonth(y: number, m: number) {
  return new Date(y, m + 1, 0).getDate();
}

/** Build a 6×7 grid (42 cells) for a month. Empty strings are blanks. */
function monthMatrix(y: number, m: number) {
  const first = new Date(y, m, 1);
  const startDow = first.getDay(); // 0..6, Sun..Sat
  const dim = daysInMonth(y, m);
  const cells: (string | number)[] = Array(42).fill("");
  for (let d = 1; d <= dim; d++) cells[startDow + d - 1] = d;
  return cells;
}

function MonthTile({ y, m }: { y: number; m: number }) {
  const today = new Date();
  const isTodayMonth = today.getFullYear() === y && today.getMonth() === m;
  const mm = useMemo(() => monthMatrix(y, m), [y, m]);

  const monthName = new Date(y, m, 1).toLocaleString("en-US", { month: "long" });

  return (
    <div className="yv-month" id={`ym-${y}-${String(m + 1).padStart(2, "0")}`} data-ym={`${y}-${m}`}>
      <div className="yv-monthname">{monthName}</div>
      <div className="yv-grid">
        {/* DOW header */}
        {["S","M","T","W","T","F","S"].map((d) => (
          <div key={`h-${d}`} className="yv-dow">{d}</div>
        ))}
        {/* days */}
        {mm.map((v, i) => {
          const isToday =
            isTodayMonth &&
            typeof v === "number" &&
            v === today.getDate();
          return (
            <div
              key={i}
              className={`yv-cell${isToday ? " is-today" : ""}`}
              aria-hidden
            >
              {v || ""}
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default function YearView({ jumpTo, onAnchorChange }: Props) {
  const hostRef = useRef<HTMLDivElement | null>(null);

  // Keep a sliding window of years (e.g., [anchor-4 .. anchor+4])
  const [startYear, setStartYear] = useState<number>(() => (jumpTo ? jumpTo.getFullYear() : new Date().getFullYear()) - 4);
  const [endYear, setEndYear]     = useState<number>(() => (jumpTo ? jumpTo.getFullYear() : new Date().getFullYear()) + 4);

  // Create list of years and each year's 12 months
  const years = useMemo(() => {
    const ys: number[] = [];
    for (let y = startYear; y <= endYear; y++) ys.push(y);
    return ys;
  }, [startYear, endYear]);

  // Infinite extend on scroll
  useEffect(() => {
    const el = hostRef.current!;
    if (!el) return;

    const onScroll = () => {
      const pad = 600; // px
      if (el.scrollTop < pad) {
        // extend upward by 3 years
        const before = el.scrollHeight;
        setStartYear((y) => y - 3);
        // after DOM paints, keep the viewport position stable
        requestAnimationFrame(() => {
          const after = el.scrollHeight;
          el.scrollTop += (after - before);
        });
      } else if (el.scrollTop + el.clientHeight > el.scrollHeight - pad) {
        // extend downward by 3 years
        setEndYear((y) => y + 3);
      }
    };

    el.addEventListener("scroll", onScroll);
    return () => el.removeEventListener("scroll", onScroll);
  }, []);

  // Observe which year is near the top to update the "anchor" for your header
  useEffect(() => {
    if (!hostRef.current || !onAnchorChange) return;
    const el = hostRef.current;
    const observer = new IntersectionObserver(
      (entries) => {
        // pick the entry nearest to the top that is intersecting
        const vis = entries
          .filter((e) => e.isIntersecting)
          .sort((a, b) => Math.abs(a.boundingClientRect.top) - Math.abs(b.boundingClientRect.top));
        const top = vis[0];
        if (top) {
          const y = parseInt((top.target as HTMLElement).dataset.year!, 10);
          // Use January to show a consistent month name in your banner
          onAnchorChange(new Date(y, 0, 1));
        }
      },
      { root: el, rootMargin: "0px 0px -70% 0px", threshold: [0, 0.01, 0.1] }
    );

    const sections = Array.from(el.querySelectorAll<HTMLElement>(".yv-yearsection"));
    sections.forEach((s) => observer.observe(s));
    return () => observer.disconnect();
  }, [years, onAnchorChange]);

  // Jump to a specific month if requested (arrows in parent)
  useEffect(() => {
    if (!jumpTo || !hostRef.current) return;

    const y = jumpTo.getFullYear();
    const m = jumpTo.getMonth();
    // Ensure the year is present
    if (y < startYear) setStartYear(y - 2);
    if (y > endYear)   setEndYear(y + 2);

    requestAnimationFrame(() => {
      const target = hostRef.current!.querySelector<HTMLElement>(`#ym-${y}-${String(m + 1).padStart(2, "0")}`);
      if (target) {
        target.scrollIntoView({ block: "start" });
      } else {
        // if not yet in DOM due to range extension, try shortly after
        setTimeout(() => {
          const again = hostRef.current!.querySelector<HTMLElement>(`#ym-${y}-${String(m + 1).padStart(2, "0")}`);
          again?.scrollIntoView({ block: "start" });
        }, 60);
      }
    });
  }, [jumpTo, startYear, endYear]);

  return (
    <div ref={hostRef} className="yv-wrap" aria-label="Year view (read-only)">
      {years.map((y) => (
        <section key={y} className="yv-yearsection" data-year={y}>
          <header className="yv-yearhdr">{y}</header>
          <div className="yv-yeargrid">
            {Array.from({ length: 12 }, (_, m) => (
              <MonthTile key={`${y}-${m}`} y={y} m={m} />
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}