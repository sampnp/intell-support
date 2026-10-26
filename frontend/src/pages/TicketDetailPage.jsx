import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import { tickets, users } from "../api/endpoints";
import { ErrorBanner, PriorityBadge, Spinner, StatusBadge } from "../components/ui";
import { useAuth } from "../context/AuthContext";
import AssignControl from "../features/tickets/AssignControl";
import CommentThread from "../features/tickets/CommentThread";
import ReplyBox from "../features/tickets/ReplyBox";
import StatusButtons from "../features/tickets/StatusButtons";
import SuggestionsPanel from "../features/tickets/SuggestionsPanel";
import Timeline from "../features/tickets/Timeline";
import { CATEGORY_LABELS, formatDateTime } from "../lib/format";
import NotFoundPage from "./NotFoundPage";

export default function TicketDetailPage() {
  const id = Number(useParams().ticketId);
  const { isAgent } = useAuth();
  const queryClient = useQueryClient();
  const [reply, setReply] = useState("");
  const [internal, setInternal] = useState(false);

  const ticketQuery = useQuery({ queryKey: ["ticket", id], queryFn: () => tickets.get(id) });
  const loaded = ticketQuery.isSuccess;
  const commentsQuery = useQuery({
    queryKey: ["ticket", id, "comments"],
    queryFn: () => tickets.comments(id),
    enabled: loaded,
  });
  const eventsQuery = useQuery({
    queryKey: ["ticket", id, "events"],
    queryFn: () => tickets.events(id),
    enabled: loaded,
  });
  const suggestionsQuery = useQuery({
    queryKey: ["ticket", id, "suggestions"],
    queryFn: () => tickets.suggestions(id),
    enabled: loaded,
  });
  const agentsQuery = useQuery({ queryKey: ["agents"], queryFn: users.agents, enabled: isAgent });

  // Any change can move status, updated_at, the timeline and the dashboard counts.
  const refreshAll = () => {
    queryClient.invalidateQueries({ queryKey: ["ticket", id] });
    queryClient.invalidateQueries({ queryKey: ["tickets"] });
    queryClient.invalidateQueries({ queryKey: ["dashboard"] });
  };

  const changeStatus = useMutation({
    mutationFn: (status) => tickets.changeStatus(id, status),
    onSuccess: refreshAll,
  });
  const assign = useMutation({
    mutationFn: (agentId) => tickets.assign(id, agentId),
    onSuccess: refreshAll,
  });
  const addComment = useMutation({
    mutationFn: () => tickets.addComment(id, { body: reply.trim(), is_internal: internal }),
    onSuccess: () => {
      setReply("");
      setInternal(false);
      refreshAll();
    },
  });
  const refreshSuggestions = useMutation({
    mutationFn: () => tickets.refreshSuggestions(id),
    onSuccess: (data) => queryClient.setQueryData(["ticket", id, "suggestions"], data),
  });

  if (ticketQuery.isPending) return <Spinner />;
  if (ticketQuery.error?.status === 404) {
    return (
      <NotFoundPage
        title="Ticket not found"
        message="This ticket doesn't exist, or you don't have access to it."
      />
    );
  }
  if (ticketQuery.error) return <ErrorBanner error={ticketQuery.error} />;

  const ticket = ticketQuery.data;
  const agentNames = new Map((agentsQuery.data ?? []).map((a) => [a.id, a.full_name]));
  const nameFor = (agentId) => agentNames.get(agentId) ?? `agent #${agentId}`;
  const insertIntoReply = (text) => setReply((current) => (current ? `${current}\n\n${text}` : text));

  return (
    <div className="space-y-4">
      <Link to="/tickets" className="text-sm text-indigo-700 hover:underline">
        ← Back to tickets
      </Link>

      <header className="card space-y-2">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <h1 className="text-xl font-semibold">
            <span className="text-slate-400">#{ticket.id}</span> {ticket.title}
          </h1>
          <div className="flex gap-2">
            <StatusBadge status={ticket.status} />
            <PriorityBadge priority={ticket.priority} />
          </div>
        </div>
        <dl className="grid gap-x-6 gap-y-1 text-sm text-slate-600 sm:grid-cols-4">
          <div><dt className="text-xs uppercase text-slate-400">Category</dt><dd>{CATEGORY_LABELS[ticket.category]}</dd></div>
          <div><dt className="text-xs uppercase text-slate-400">Opened by</dt><dd>{ticket.created_by.full_name}</dd></div>
          <div><dt className="text-xs uppercase text-slate-400">Assignee</dt><dd>{ticket.assigned_to?.full_name ?? "Unassigned"}</dd></div>
          <div><dt className="text-xs uppercase text-slate-400">Opened</dt><dd>{formatDateTime(ticket.created_at)}</dd></div>
        </dl>
        <p className="whitespace-pre-line pt-2 text-sm text-slate-800">{ticket.description}</p>
      </header>

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <section className="card space-y-3">
            <h2 className="font-semibold">Conversation</h2>
            {commentsQuery.data ? <CommentThread comments={commentsQuery.data} /> : <Spinner />}
          </section>
          <section className="card">
            <ReplyBox
              value={reply}
              onChange={setReply}
              internal={internal}
              onInternalChange={setInternal}
              onSubmit={() => addComment.mutate()}
              canWriteInternal={isAgent}
              closed={ticket.status === "closed"}
              submitting={addComment.isPending}
              error={addComment.error}
            />
          </section>
        </div>

        <aside className="space-y-4">
          {(ticket.allowed_transitions.length > 0 || isAgent) && (
            <section className="card space-y-3">
              <h2 className="font-semibold">Actions</h2>
              <StatusButtons
                allowed={ticket.allowed_transitions}
                onChange={(status) => changeStatus.mutate(status)}
                disabled={changeStatus.isPending}
              />
              <ErrorBanner error={changeStatus.error} />
              {isAgent && ticket.status !== "closed" && (
                <AssignControl
                  ticket={ticket}
                  agents={agentsQuery.data}
                  onAssign={(agentId) => assign.mutate(agentId)}
                  pending={assign.isPending}
                  error={assign.error}
                />
              )}
            </section>
          )}

          <SuggestionsPanel
            suggestions={suggestionsQuery.data}
            loading={suggestionsQuery.isPending}
            error={suggestionsQuery.error ?? refreshSuggestions.error}
            canInsert={isAgent && ticket.status !== "closed"}
            onInsert={insertIntoReply}
            onRefresh={() => refreshSuggestions.mutate()}
            refreshing={refreshSuggestions.isPending}
          />

          <section className="card space-y-3">
            <h2 className="font-semibold">Activity</h2>
            {eventsQuery.data ? <Timeline events={eventsQuery.data} nameFor={nameFor} /> : <Spinner />}
          </section>
        </aside>
      </div>
    </div>
  );
}
