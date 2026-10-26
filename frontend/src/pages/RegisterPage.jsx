import { useState } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";

import { ErrorBanner, FieldError } from "../components/ui";
import { useAuth } from "../context/AuthContext";
import { fieldErrors } from "../lib/errors";

function validate({ full_name, email, password }) {
  const errors = {};
  if (!full_name.trim()) errors.full_name = "Enter your name.";
  if (!/^\S+@\S+\.\S+$/.test(email.trim())) errors.email = "Enter a valid email address.";
  if (password.length < 8) errors.password = "Use at least 8 characters.";
  return errors;
}

export default function RegisterPage() {
  const { user, register } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState({ full_name: "", email: "", password: "" });
  const [errors, setErrors] = useState({});
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  if (user) return <Navigate to="/" replace />;

  const update = (field) => (event) => setForm({ ...form, [field]: event.target.value });

  async function handleSubmit(event) {
    event.preventDefault();
    const clientErrors = validate(form);
    setErrors(clientErrors);
    setError(null);
    if (Object.keys(clientErrors).length) return;
    setSubmitting(true);
    try {
      await register({ ...form, full_name: form.full_name.trim(), email: form.email.trim() });
      navigate("/tickets", { replace: true });
    } catch (err) {
      setErrors(fieldErrors(err));
      setError(err);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="mx-auto mt-16 max-w-sm px-4">
      <h1 className="mb-6 text-2xl font-semibold">Create an account</h1>
      <form onSubmit={handleSubmit} className="card space-y-4" noValidate>
        <ErrorBanner error={error} />
        <div>
          <label className="label" htmlFor="full_name">Full name</label>
          <input id="full_name" className="input" value={form.full_name} onChange={update("full_name")} />
          <FieldError message={errors.full_name} />
        </div>
        <div>
          <label className="label" htmlFor="email">Email</label>
          <input id="email" type="email" className="input" value={form.email} onChange={update("email")} />
          <FieldError message={errors.email} />
        </div>
        <div>
          <label className="label" htmlFor="password">Password</label>
          <input
            id="password"
            type="password"
            className="input"
            autoComplete="new-password"
            value={form.password}
            onChange={update("password")}
          />
          <FieldError message={errors.password} />
        </div>
        <button type="submit" className="btn-primary w-full" disabled={submitting}>
          {submitting ? "Creating account…" : "Create account"}
        </button>
        <p className="text-center text-sm text-slate-600">
          Already registered?{" "}
          <Link to="/login" className="font-medium text-indigo-700 hover:underline">
            Sign in
          </Link>
        </p>
      </form>
    </div>
  );
}
