import { useEffect, useState } from 'react';
import FullCalendar from '@fullcalendar/react';
import dayGridPlugin from '@fullcalendar/daygrid';
import '@fullcalendar/common/main.css';
import '@fullcalendar/daygrid/main.css';
import './index.css'; // keeps Tailwind

interface EventOut {
  id: number;
  title: string;
  start: string;
  end: string;
}

export default function App() {
  const [events, setEvents] = useState<EventOut[]>([]);

  useEffect(() => {
    fetch('https://silver-goldfish-44r7x5x9qg5255jv-8000.app.github.dev/events')
      .then((r) => r.json())
      .then(setEvents);
  }, []);

  return (
    <div className="min-h-screen bg-gray-100 flex flex-col">
      <header className="text-center py-4 text-3xl font-semibold">Cal</header>
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