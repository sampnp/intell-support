import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { AuthContext } from "../context/AuthContext";
import RequireAuth from "./RequireAuth";

const USER = { id: 1, full_name: "Dana Whitfield", role: "user" };
const AGENT = { id: 2, full_name: "Priya Shah", role: "agent" };

function renderAt(path, { user = null, loading = false } = {}) {
  render(
    <AuthContext.Provider value={{ user, loading, isAgent: user?.role === "agent" }}>
      <MemoryRouter
        initialEntries={[path]}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <Routes>
          <Route path="/login" element={<p>login page</p>} />
          <Route path="/" element={<p>home page</p>} />
          <Route
            path="/private"
            element={
              <RequireAuth>
                <p>private page</p>
              </RequireAuth>
            }
          />
          <Route
            path="/agents-only"
            element={
              <RequireAuth role="agent">
                <p>agent page</p>
              </RequireAuth>
            }
          />
        </Routes>
      </MemoryRouter>
    </AuthContext.Provider>,
  );
}

describe("RequireAuth", () => {
  it("sends a logged-out visitor to the login page", () => {
    renderAt("/private");
    expect(screen.getByText("login page")).toBeInTheDocument();
    expect(screen.queryByText("private page")).not.toBeInTheDocument();
  });

  it("shows a signed-in user's page", () => {
    renderAt("/private", { user: USER });
    expect(screen.getByText("private page")).toBeInTheDocument();
  });

  it("keeps users out of agent pages", () => {
    renderAt("/agents-only", { user: USER });
    expect(screen.getByText("home page")).toBeInTheDocument();
    expect(screen.queryByText("agent page")).not.toBeInTheDocument();
  });

  it("lets agents into agent pages", () => {
    renderAt("/agents-only", { user: AGENT });
    expect(screen.getByText("agent page")).toBeInTheDocument();
  });

  it("waits while the session is being checked", () => {
    renderAt("/private", { loading: true });
    expect(screen.getByRole("status")).toHaveTextContent("Checking your session");
    expect(screen.queryByText("login page")).not.toBeInTheDocument();
  });
});
