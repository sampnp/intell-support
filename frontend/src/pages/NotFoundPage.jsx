import { Link } from "react-router-dom";

export default function NotFoundPage({ title = "Page not found", message }) {
  return (
    <div className="card mx-auto mt-10 max-w-md text-center">
      <h1 className="mb-2 text-xl font-semibold">{title}</h1>
      <p className="mb-4 text-sm text-slate-600">
        {message ?? "There is nothing at this address."}
      </p>
      <Link to="/" className="btn-primary">
        Go home
      </Link>
    </div>
  );
}
