import { useEffect, useState } from "react";
import FullCalendar from "@fullcalendar/react";
import dayGridPlugin from "@fullcalendar/daygrid";
import "@fullcalendar/core/main.css";     // v6.1.8 file name
import "@fullcalendar/daygrid/main.css";

interface EventOut {
  id: string;      // FullCalendar wants string ids
  title: string;
  start: string;
  end: string;
}

export default function App() {
  const [events, setEvents] = useState<EventOut[]>([]);

  useEffect(() => {
    fetch(
      "https://silver-goldfish-44r7x5x9qg5255jv-8000.app.github.dev/events"
    )
      .then((r) => r.json())
      .then((raw) =>
        setEvents(
          raw.map((e: any) => ({
            ...e,
            id: String(e.id), // cast to string

            // if end === start (zero-length) add +1 h so dayGrid can render it
            end:
              e.end === e.start
                ? new Date(
                    new Date(e.start).getTime() + 60 * 60 * 1000
                  ).toISOString()
                : e.end,
          }))
        )
      );
  }, []);

  return (
    <div className="min-h-screen bg-gray-100 flex flex-col">
      <header className="text-center py-4 text-3xl font-semibold">Cal</header>

      {/* pink bar proves Tailwind is compiling – remove whenever you like */}
      <div className="bg-pink-500 text-white p-4">Tailwind works!</div>

      <main className="flex-1 px-4">
        <FullCalendar
          plugins={[dayGridPlugin]}
          initialView="dayGridWeek"
          events={events}
          height="auto"
        />
      </main>
    </div>
  );
}