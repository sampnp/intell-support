import { ErrorBanner } from "../../components/ui";

/** Agents only. "Unassigned" sends agent_id: null. */
export default function AssignControl({ ticket, agents = [], onAssign, pending, error }) {
  const current = ticket.assigned_to?.id ?? "";
  return (
    <div className="space-y-1">
      <label className="label" htmlFor="assignee">Assignee</label>
      <select
        id="assignee"
        className="input"
        value={current}
        disabled={pending}
        onChange={(e) => onAssign(e.target.value ? Number(e.target.value) : null)}
      >
        <option value="">Unassigned</option>
        {agents.map((agent) => (
          <option key={agent.id} value={agent.id}>
            {agent.full_name}
          </option>
        ))}
      </select>
      <ErrorBanner error={error} />
    </div>
  );
}
