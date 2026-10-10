"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef } from "react";

const EVERY_MS = 3_000;
const RENEW_MS = 60_000;

// Live chat screens show new offers and messages by refreshing every 3 seconds (issue #138).
// The customer chat also renews its session while a live chat is open (R47).
export function Refresh({ renew }: { renew?: () => Promise<void> }) {
  const router = useRouter();
  // A ref, so the renewal clock survives the new props each refresh brings.
  const renewed = useRef(0);
  useEffect(() => {
    const timer = setInterval(() => {
      if (renew && Date.now() - renewed.current >= RENEW_MS) {
        renewed.current = Date.now();
        void renew();
      }
      router.refresh();
    }, EVERY_MS);
    return () => clearInterval(timer);
  }, [router, renew]);
  return null;
}
