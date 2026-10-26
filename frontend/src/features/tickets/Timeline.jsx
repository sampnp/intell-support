import { describeEvent, formatDateTime } from "../../lib/format";

export default function Timeline({ events, nameFor }) {
  return (
    <ol className="space-y-2 border-l border-slate-200 pl-4 text-sm">
      {events.map((event) => (
        <li key={event.id} className="relative">
          <span className="absolute -left-[1.3rem] top-1.5 h-2 w-2 rounded-full bg-slate-300" />
          <span className="font-medium">{event.actor.full_name}</span>{" "}
          <span className="text-slate-700">{describeEvent(event, nameFor)}</span>
          <div className="text-xs text-slate-400">{formatDateTime(event.created_at)}</div>
        </li>
      ))}
    </ol>
  );
}
