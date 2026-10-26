import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { tickets } from "../api/endpoints";
import { ErrorBanner, FieldError } from "../components/ui";
import { fieldErrors } from "../lib/errors";
import { CATEGORIES, CATEGORY_LABELS, PRIORITIES, PRIORITY_LABELS } from "../lib/format";

// Same limits as the API (docs/PLAN.md §5).
function validate({ title, description, category }) {
  const errors = {};
  const t = title.trim();
  const d = description.trim();
  if (t.length < 5 || t.length > 200) errors.title = "Title must be 5–200 characters.";
  if (d.length < 10 || d.length > 5000) errors.description = "Description must be 10–5000 characters.";
  if (!category) errors.category = "Choose a category.";
  return errors;
}

export default function NewTicketPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [form, setForm] = useState({ title: "", description: "", category: "", priority: "medium" });
  const [errors, setErrors] = useState({});

  const create = useMutation({
    mutationFn: tickets.create,
    onSuccess: (ticket) => {
      queryClient.invalidateQueries({ queryKey: ["tickets"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      // The suggestions snapshot was taken on creation; the detail page shows it.
      navigate(`/tickets/${ticket.id}`);
    },
    onError: (error) => setErrors(fieldErrors(error)),
  });

  const update = (field) => (event) => setForm({ ...form, [field]: event.target.value });

  function handleSubmit(event) {
    event.preventDefault();
    const clientErrors = validate(form);
    setErrors(clientErrors);
    if (Object.keys(clientErrors).length) return;
    create.mutate({ ...form, title: form.title.trim(), description: form.description.trim() });
  }

  return (
    <div className="mx-auto max-w-2xl space-y-4">
      <h1 className="text-xl font-semibold">New ticket</h1>
      <form onSubmit={handleSubmit} className="card space-y-4" noValidate>
        <ErrorBanner error={create.error} />
        <div>
          <label className="label" htmlFor="title">Title</label>
          <input id="title" className="input" maxLength={200} value={form.title} onChange={update("title")} />
          <FieldError message={errors.title} />
        </div>
        <div>
          <label className="label" htmlFor="description">Description</label>
          <textarea
            id="description"
            className="input min-h-40"
            maxLength={5000}
            value={form.description}
            onChange={update("description")}
            placeholder="What happened, what did you expect, and what have you tried?"
          />
          <div className="flex justify-between">
            <FieldError message={errors.description} />
            <span className="ml-auto text-xs text-slate-400">{form.description.length}/5000</span>
          </div>
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <label className="label" htmlFor="category">Category</label>
            <select id="category" className="input" value={form.category} onChange={update("category")}>
              <option value="">Choose…</option>
              {CATEGORIES.map((c) => (
                <option key={c} value={c}>{CATEGORY_LABELS[c]}</option>
              ))}
            </select>
            <FieldError message={errors.category} />
          </div>
          <div>
            <label className="label" htmlFor="priority">Priority</label>
            <select id="priority" className="input" value={form.priority} onChange={update("priority")}>
              {PRIORITIES.map((p) => (
                <option key={p} value={p}>{PRIORITY_LABELS[p]}</option>
              ))}
            </select>
          </div>
        </div>
        <div className="flex justify-end gap-2">
          <button type="button" className="btn-secondary" onClick={() => navigate(-1)}>
            Cancel
          </button>
          <button type="submit" className="btn-primary" disabled={create.isPending}>
            {create.isPending ? "Creating…" : "Create ticket"}
          </button>
        </div>
      </form>
    </div>
  );
}
