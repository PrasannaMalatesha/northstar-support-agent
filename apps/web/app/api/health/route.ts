import { NextResponse } from "next/server";

const apiUrl = process.env.FASTAPI_URL ?? "http://127.0.0.1:8000";

export async function GET() {
  try {
    const response = await fetch(`${apiUrl}/health`, { cache: "no-store" });
    if (!response.ok) {
      return NextResponse.json({ status: "waking" }, { status: 503 });
    }
    return NextResponse.json({ status: "ok" });
  } catch {
    return NextResponse.json({ status: "waking" }, { status: 503 });
  }
}
