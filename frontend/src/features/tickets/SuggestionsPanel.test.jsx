import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import SuggestionsPanel, { suggestionQuote } from "./SuggestionsPanel";

const BILLING = {
  chunk_id: "c1",
  document_id: 2,
  document_title: "Billing & Refund Policy",
  page: 2,
  snippet: "Duplicate charges are always refunded in full.",
  score: 0.781,
};
const SYNC = {
  chunk_id: "c2",
  document_id: 4,
  document_title: "Sync troubleshooting",
  page: null,
  snippet: "Conflicted copies appear when a file changes in two places.",
  score: 0.65,
};

const snapshot = (overrides = {}) => ({
  mode: "semantic",
  insufficient: false,
  updated_at: new Date().toISOString(),
  results: [BILLING, SYNC],
  ...overrides,
});

describe("SuggestionsPanel", () => {
  it("shows the passages with their sources and scores", () => {
    render(<SuggestionsPanel suggestions={snapshot()} onRefresh={() => {}} />);

    expect(screen.getAllByRole("listitem")).toHaveLength(2);
    expect(screen.getByText("Billing & Refund Policy")).toBeInTheDocument();
    expect(screen.getByText(", p. 2")).toBeInTheDocument();
    expect(screen.getByText("score 0.78")).toBeInTheDocument();
    expect(screen.getByText(BILLING.snippet)).toBeInTheDocument();
    expect(screen.getByText("Semantic search")).toBeInTheDocument();
  });

  it("shows the keyword badge when the fallback was used", () => {
    render(<SuggestionsPanel suggestions={snapshot({ mode: "keyword" })} onRefresh={() => {}} />);

    expect(screen.getByText("Keyword search")).toBeInTheDocument();
  });

  it("says when the knowledge base has nothing good enough", () => {
    render(
      <SuggestionsPanel
        suggestions={snapshot({ insufficient: true, results: [] })}
        onRefresh={() => {}}
      />,
    );

    expect(screen.getByText(/Not enough information in the knowledge base/)).toBeInTheDocument();
    expect(screen.queryAllByRole("listitem")).toHaveLength(0);
  });

  it("says when suggestions could not be produced at all", () => {
    render(
      <SuggestionsPanel
        suggestions={snapshot({ mode: null, insufficient: true, results: [] })}
        onRefresh={() => {}}
      />,
    );

    expect(screen.getByText(/not available right now/)).toBeInTheDocument();
  });

  it("hides 'Insert into reply' from users", () => {
    render(<SuggestionsPanel suggestions={snapshot()} canInsert={false} onRefresh={() => {}} />);

    expect(screen.queryByRole("button", { name: "Insert into reply" })).not.toBeInTheDocument();
  });

  it("lets agents insert a passage with its source", async () => {
    const onInsert = vi.fn();
    render(
      <SuggestionsPanel suggestions={snapshot()} canInsert onInsert={onInsert} onRefresh={() => {}} />,
    );

    const buttons = screen.getAllByRole("button", { name: "Insert into reply" });
    expect(buttons).toHaveLength(2);
    await userEvent.setup().click(buttons[0]);

    expect(onInsert).toHaveBeenCalledWith(
      "Duplicate charges are always refunded in full.\n\n(Source: Billing & Refund Policy, p. 2)",
    );
  });

  it("omits the page for text documents", () => {
    expect(suggestionQuote(SYNC)).toBe(
      "Conflicted copies appear when a file changes in two places.\n\n(Source: Sync troubleshooting)",
    );
  });

  it("refreshes on demand", async () => {
    const onRefresh = vi.fn();
    render(<SuggestionsPanel suggestions={snapshot()} onRefresh={onRefresh} />);

    await userEvent.setup().click(screen.getByRole("button", { name: "Refresh" }));

    expect(onRefresh).toHaveBeenCalledOnce();
  });
});
