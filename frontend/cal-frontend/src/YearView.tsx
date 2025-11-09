import { useEffect, useMemo, useRef, useState } from "react";

/**
 * Scrollable infinite Year view.
 * - opens centered on jumpTo/current month
 * - extends as you scroll
 * - month tiles are clickable to open Month view in the parent
 */
type Props = {
  jumpTo?: Date;
  onAnchorChange?: (d: Date) => void;
  onPick?: (y: number, mZeroBased: number) => void; // click a month tile
};

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

function MonthTile({ y, m, onPick }: { y: number; m: number; onPick?: (y: number, m: number) => void }) {
  const today = new Date();
  const isTodayMonth = today.getFullYear() === y && today.getMonth() === m;
  const mm = useMemo(() => monthMatrix(y, m), [y, m]);
  const monthName = new Date(y, m, 1).toLocaleString("en-US", { month: "long" });

  const handleClick = () => onPick?.(y, m);
  const handleKey = (e: React.KeyboardEvent<HTMLDivElement>) => {
    if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onPick?.(y, m); }
  };

  return (
    <div
      className="yv-month"
      id={`ym-${y}-${String(m + 1).padStart(2, "0")}`}
      data-ym={`${y}-${m}`}
      onClick={handleClick}
      tabIndex={0}
      onKeyDown={handleKey}
      role="button"
      aria-label={`Open ${monthName} ${y}`}
    >
      <div className="yv-monthname">{monthName}</div>
      <div className="yv-grid">
        {/* DOW header */}
        {["S","M","T","W","T","F","S"].map((d) => (
          <div key={`h-${d}`} className="yv-dow">{d}</div>
        ))}
        {/* days */}
        {mm.map((v, i) => {
          const isToday = isTodayMonth && typeof v === "number" && v === today.getDate();
          return (
            <div key={i} className={`yv-cell${isToday ? " is-today" : ""}`} aria-hidden>
              {v || ""}
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default function YearView({ jumpTo, onAnchorChange, onPick }: Props) {
  const hostRef = useRef<HTMLDivElement | null>(null);

  const base = jumpTo ?? new Date();
  const baseYear = base.getFullYear();
  const [startYear, setStartYear] = useState<number>(baseYear - 20);
  const [endYear, setEndYear]     = useState<number>(baseYear + 20);

  const years = useMemo(() => {
    const ys: number[] = [];
    for (let y = startYear; y <= endYear; y++) ys.push(y);
    return ys;
  }, [startYear, endYear]);

  // Throttled scroll extender — avoids jank while keeping “infinite” feel.
  useEffect(() => {
    const el = hostRef.current;
    if (!el) return;

    let raf = 0;
    const PAD = 800; // px

    const onScroll = () => {
      if (raf) return;
      raf = requestAnimationFrame(() => {
        raf = 0;
        const nearTop = el.scrollTop < PAD;
        const nearBottom = el.scrollTop + el.clientHeight > el.scrollHeight - PAD;

        if (nearTop) {
          const before = el.scrollHeight;
          setStartYear((y) => y - 5);
          // preserve viewport after DOM grows above
          requestAnimationFrame(() => {
            const after = el.scrollHeight;
            el.scrollTop += (after - before);
          });
        } else if (nearBottom) {
          setEndYear((y) => y + 5);
        }
      });
    };

    el.addEventListener("scroll", onScroll);
    return () => {
      el.removeEventListener("scroll", onScroll);
      if (raf) cancelAnimationFrame(raf);
    };
  }, []);

  // Observe which year is near the top to update the “anchor”
  useEffect(() => {
    if (!hostRef.current || !onAnchorChange) return;
    const el = hostRef.current;

    const observer = new IntersectionObserver(
      (entries) => {
        const vis = entries
          .filter((e) => e.isIntersecting)
          .sort((a, b) => Math.abs(a.boundingClientRect.top) - Math.abs(b.boundingClientRect.top));
        const top = vis[0];
        if (top) {
          const y = parseInt((top.target as HTMLElement).dataset.year!, 10);
          onAnchorChange(new Date(y, 0, 1));
        }
      },
      { root: el, rootMargin: "0px 0px -70% 0px", threshold: [0, 0.01, 0.1] }
    );

    const sections = Array.from(el.querySelectorAll<HTMLElement>(".yv-yearsection"));
    sections.forEach((s) => observer.observe(s));
    return () => observer.disconnect();
  }, [years, onAnchorChange]);

  // Jump to a month (used by outer arrows and when switching into Year view)
  useEffect(() => {
    const el = hostRef.current;
    if (!el) return;

    const target = jumpTo ?? base;
    const y = target.getFullYear();
    const m = target.getMonth();

    if (y < startYear) setStartYear(y - 6);
    if (y > endYear)   setEndYear(y + 6);

    const seek = () => {
      const node = el.querySelector<HTMLElement>(`#ym-${y}-${String(m + 1).padStart(2, "0")}`);
      if (node) node.scrollIntoView({ block: "nearest" }); // gentler than "start" (prevents slight downward nudge)
      else setTimeout(seek, 40);
    };
    seek();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jumpTo, startYear, endYear]);

  return (
    <div ref={hostRef} className="yv-wrap" aria-label="Year view">
      {years.map((y) => (
        <section key={y} className="yv-yearsection" data-year={y}>
          <header className="yv-yearhdr">{y}</header>
          <div className="yv-yeargrid">
            {Array.from({ length: 12 }, (_, m) => (
              <MonthTile key={`${y}-${m}`} y={y} m={m} onPick={onPick} />
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}