"use client";

import { useEffect, useState } from "react";

export function LoginForm({
  action,
  error,
}: {
  action: (formData: FormData) => void | Promise<void>;
  error?: string;
}) {
  const [awake, setAwake] = useState<boolean | null>(null);

  useEffect(() => {
    let stopped = false;

    async function ping() {
      try {
        const response = await fetch("/api/health", { cache: "no-store" });
        if (!stopped) {
          setAwake(response.ok);
        }
      } catch {
        if (!stopped) {
          setAwake(false);
        }
      }
    }

    void ping();
    const timer = window.setInterval(() => void ping(), 3000);
    return () => {
      stopped = true;
      window.clearInterval(timer);
    };
  }, []);

  return (
    <form action={action}>
      {awake === false ? (
        <p className="status" role="status">
          Waking the server.
        </p>
      ) : null}
      {error ? (
        <p className="error" role="alert">
          {error}
        </p>
      ) : null}
      <label>
        Email
        <input
          name="email"
          type="email"
          autoComplete="username"
          required
          spellCheck={false}
        />
      </label>
      <label>
        Password
        <input
          name="password"
          type="password"
          autoComplete="current-password"
          required
        />
      </label>
      <button type="submit" disabled={awake === false}>
        Sign in
      </button>
    </form>
  );
}
