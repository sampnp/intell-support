import { formatDateTime } from "../../lib/format";

/** The conversation. Internal notes only ever reach agents (the API filters them for users). */
export default function CommentThread({ comments }) {
  if (comments.length === 0) {
    return <p className="text-sm text-slate-500">No replies yet.</p>;
  }
  return (
    <ul className="space-y-3">
      {comments.map((comment) => (
        <li
          key={comment.id}
          className={`rounded-lg border p-3 ${
            comment.is_internal ? "border-amber-300 bg-amber-50" : "border-slate-200 bg-white"
          }`}
        >
          <div className="mb-1 flex flex-wrap items-center gap-2 text-sm">
            <span className="font-medium">{comment.author.full_name}</span>
            {comment.author.role === "agent" && (
              <span className="rounded bg-indigo-50 px-1.5 text-xs text-indigo-700">Agent</span>
            )}
            {comment.is_internal && (
              <span className="rounded bg-amber-200 px-1.5 text-xs font-medium text-amber-900">
                Internal note
              </span>
            )}
            <span className="ml-auto text-xs text-slate-500">{formatDateTime(comment.created_at)}</span>
          </div>
          <p className="whitespace-pre-line text-sm text-slate-800">{comment.body}</p>
        </li>
      ))}
    </ul>
  );
}
