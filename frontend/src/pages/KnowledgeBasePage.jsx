import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";

import { kb } from "../api/endpoints";
import { ErrorBanner, ModeBadge, Spinner } from "../components/ui";
import { useAuth } from "../context/AuthContext";
import { formatRelative } from "../lib/format";

const DOC_STATUS_STYLES = {
  processing: "bg-sky-100 text-sky-800",
  ready: "bg-emerald-100 text-emerald-800",
  failed: "bg-red-100 text-red-800",
};

function SearchPanel() {
  const [form, setForm] = useState({ q: "", mode: "auto", k: 3 });
  const search = useMutation({ mutationFn: (params) => kb.search(params) });

  function handleSubmit(event) {
    event.preventDefault();
    if (form.q.trim()) search.mutate({ ...form, q: form.q.trim() });
  }

  const result = search.data;
  return (
    <section className="card space-y-3">
      <h2 className="font-semibold">Search the knowledge base</h2>
      <form onSubmit={handleSubmit} className="flex flex-wrap gap-2">
        <input
          className="input flex-1"
          type="search"
          placeholder="e.g. I was charged twice this month"
          aria-label="Search query"
          maxLength={500}
          value={form.q}
          onChange={(e) => setForm({ ...form, q: e.target.value })}
        />
        <select
          className="input w-auto"
          aria-label="Search mode"
          value={form.mode}
          onChange={(e) => setForm({ ...form, mode: e.target.value })}
        >
          <option value="auto">Auto (semantic, keyword fallback)</option>
          <option value="semantic">Semantic only</option>
          <option value="keyword">Keyword only</option>
        </select>
        <select
          className="input w-auto"
          aria-label="Number of results"
          value={form.k}
          onChange={(e) => setForm({ ...form, k: Number(e.target.value) })}
        >
          {[3, 5, 10].map((k) => (
            <option key={k} value={k}>{k} results</option>
          ))}
        </select>
        <button type="submit" className="btn-primary" disabled={search.isPending || !form.q.trim()}>
          {search.isPending ? "Searching…" : "Search"}
        </button>
      </form>

      <ErrorBanner error={search.error} />
      {result && (
        <div className="space-y-2">
          <ModeBadge mode={result.mode} />
          {result.insufficient ? (
            <p className="rounded-md bg-slate-50 px-3 py-2 text-sm text-slate-600">
              Not enough information in the knowledge base to answer this.
            </p>
          ) : (
            <ol className="space-y-2">
              {result.results.map((hit) => (
                <li key={hit.chunk_id} className="rounded-md border border-slate-200 p-3">
                  <div className="mb-1 flex justify-between gap-2 text-sm">
                    <span className="font-medium">
                      {hit.document_title}
                      {hit.page ? <span className="text-slate-500">, p. {hit.page}</span> : null}
                    </span>
                    <span className="text-xs text-slate-500">score {hit.score.toFixed(2)}</span>
                  </div>
                  <p className="whitespace-pre-line text-sm text-slate-700">{hit.snippet}</p>
                </li>
              ))}
            </ol>
          )}
        </div>
      )}
    </section>
  );
}

function UploadForm() {
  const queryClient = useQueryClient();
  const fileInput = useRef(null);
  const [file, setFile] = useState(null);
  const [title, setTitle] = useState("");

  const upload = useMutation({
    mutationFn: () => kb.upload(file, title.trim()),
    onSuccess: () => {
      setFile(null);
      setTitle("");
      if (fileInput.current) fileInput.current.value = "";
      queryClient.invalidateQueries({ queryKey: ["kb-documents"] });
    },
  });

  return (
    <section className="card space-y-3">
      <h2 className="font-semibold">Upload a document</h2>
      <form
        className="flex flex-wrap items-end gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (file) upload.mutate();
        }}
      >
        <div className="min-w-56 flex-1">
          <label className="label" htmlFor="kb-file">PDF or TXT file</label>
          <input
            id="kb-file"
            ref={fileInput}
            type="file"
            accept=".pdf,.txt"
            className="input"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
        </div>
        <div className="min-w-56 flex-1">
          <label className="label" htmlFor="kb-title">Title (optional)</label>
          <input
            id="kb-title"
            className="input"
            maxLength={200}
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Defaults to the file name"
          />
        </div>
        <button type="submit" className="btn-primary" disabled={!file || upload.isPending}>
          {upload.isPending ? "Uploading…" : "Upload"}
        </button>
      </form>
      <ErrorBanner error={upload.error} />
    </section>
  );
}

function DocumentTable() {
  const queryClient = useQueryClient();
  const documents = useQuery({
    queryKey: ["kb-documents"],
    queryFn: kb.documents,
    // Processing happens in the background; poll until every document has settled.
    refetchInterval: (query) =>
      query.state.data?.some((doc) => doc.status === "processing") ? 2000 : false,
  });
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["kb-documents"] });
  const remove = useMutation({ mutationFn: kb.remove, onSuccess: refresh });
  const reindex = useMutation({ mutationFn: kb.reindex, onSuccess: refresh });

  if (documents.isPending) return <Spinner />;
  return (
    <section className="card space-y-3 overflow-x-auto">
      <h2 className="font-semibold">Documents</h2>
      <ErrorBanner error={documents.error ?? remove.error ?? reindex.error} />
      <table className="min-w-full divide-y divide-slate-200 text-sm">
        <thead className="text-left text-xs uppercase text-slate-500">
          <tr>
            <th className="py-2 pr-3">Title</th>
            <th className="py-2 pr-3">Status</th>
            <th className="py-2 pr-3">Chunks</th>
            <th className="py-2 pr-3">Indexed</th>
            <th className="py-2 pr-3">Uploaded</th>
            <th className="py-2" />
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {documents.data?.length === 0 && (
            <tr><td colSpan={6} className="py-6 text-center text-slate-500">No documents yet.</td></tr>
          )}
          {documents.data?.map((doc) => (
            <tr key={doc.id} className="align-top">
              <td className="py-2 pr-3">
                <div className="font-medium">{doc.title}</div>
                <div className="text-xs text-slate-500">{doc.filename}</div>
                {doc.error_message && <div className="text-xs text-red-700">{doc.error_message}</div>}
              </td>
              <td className="py-2 pr-3">
                <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${DOC_STATUS_STYLES[doc.status]}`}>
                  {doc.status}
                </span>
              </td>
              <td className="py-2 pr-3">{doc.chunk_count}</td>
              <td className="py-2 pr-3">{doc.vector_indexed ? "Yes" : "No"}</td>
              <td className="py-2 pr-3 text-slate-500">{formatRelative(doc.created_at)}</td>
              <td className="space-x-2 whitespace-nowrap py-2 text-right">
                <button
                  type="button"
                  className="btn-secondary"
                  disabled={doc.status !== "ready" || reindex.isPending}
                  onClick={() => reindex.mutate(doc.id)}
                >
                  Reindex
                </button>
                <button
                  type="button"
                  className="btn-danger"
                  disabled={remove.isPending}
                  onClick={() => {
                    if (window.confirm(`Delete "${doc.title}" from the knowledge base?`)) {
                      remove.mutate(doc.id);
                    }
                  }}
                >
                  Delete
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

export default function KnowledgeBasePage() {
  const { isAgent } = useAuth();
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Knowledge base</h1>
      <SearchPanel />
      {/* Managing documents is agent-only in the API as well. */}
      {isAgent && (
        <>
          <UploadForm />
          <DocumentTable />
        </>
      )}
    </div>
  );
}
