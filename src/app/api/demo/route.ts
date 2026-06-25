import { NextResponse } from "next/server";

export const runtime = "nodejs";

const EMAIL_RE = /^[\w.+-]+@[\w-]+\.[\w.-]+$/;
const PHONE_RE = /^(?:\+?91[-\s]?)?[6-9]\d{9}$/;

/**
 * POST /api/demo — capture a "Book a demo" request from the landing page.
 *
 * This is a pitch/marketing site, so there is no database. We validate the
 * input and log the lead server-side; wiring this to a CRM, email, or sheet is
 * a one-line change for whoever takes this to production.
 */
export async function POST(req: Request) {
  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "Invalid request." }, { status: 400 });
  }

  const { contact } = (body ?? {}) as { contact?: string };
  const value = (contact ?? "").trim();

  if (!value) {
    return NextResponse.json({ error: "A work email or phone is required." }, { status: 400 });
  }

  const isEmail = EMAIL_RE.test(value);
  const isPhone = PHONE_RE.test(value.replace(/\s/g, ""));
  if (!isEmail && !isPhone) {
    return NextResponse.json(
      { error: "Enter a valid work email or Indian phone number." },
      { status: 422 },
    );
  }

  console.log(`[VoClyp demo request] ${isEmail ? "email" : "phone"}: ${value}`);

  return NextResponse.json({
    ok: true,
    message: "Thanks, we've got your details. We'll reach out within one business day.",
  });
}
