// src/datetime.ts
// Helpers to convert between <input type="datetime-local"> values (local/naive)
// and ISO strings that include timezone (UTC "Z").

// yyyy-mm-ddThh:mm in the user's local time
export function nowLocalInput(): string {
  const d = new Date();
  d.setSeconds(0, 0);
  return toLocalInput(d);
}

function toLocalInput(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

// ISO (with timezone) -> local input value
export function isoToLocalInput(iso: string): string {
  const d = new Date(iso);
  return toLocalInput(d);
}

// local input value -> ISO UTC (Z)
export function localInputToISO(local: string): string {
  // new Date("yyyy-mm-ddThh:mm") treats it as local time; toISOString() converts to UTC Z
  return new Date(local).toISOString();
}