import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import StatusButtons from "./StatusButtons";

describe("StatusButtons", () => {
  it("renders exactly the allowed transitions", () => {
    render(<StatusButtons allowed={["in_progress", "resolved"]} onChange={() => {}} />);

    const buttons = screen.getAllByRole("button");
    expect(buttons.map((b) => b.textContent)).toEqual(["Mark in progress", "Resolve"]);
  });

  it("gives an owner of a resolved ticket Close and Reopen", () => {
    render(<StatusButtons allowed={["closed", "open"]} onChange={() => {}} />);

    expect(screen.getAllByRole("button").map((b) => b.textContent)).toEqual([
      "Close ticket",
      "Reopen",
    ]);
  });

  it("renders nothing when no move is allowed", () => {
    const { container } = render(<StatusButtons allowed={[]} onChange={() => {}} />);

    expect(container).toBeEmptyDOMElement();
  });

  it("reports the chosen status", async () => {
    const onChange = vi.fn();
    render(<StatusButtons allowed={["waiting_for_user", "resolved"]} onChange={onChange} />);

    await userEvent.setup().click(screen.getByRole("button", { name: "Resolve" }));

    expect(onChange).toHaveBeenCalledWith("resolved");
  });

  it("can be disabled while a change is in flight", () => {
    render(<StatusButtons allowed={["resolved"]} onChange={() => {}} disabled />);

    expect(screen.getByRole("button", { name: "Resolve" })).toBeDisabled();
  });
});
