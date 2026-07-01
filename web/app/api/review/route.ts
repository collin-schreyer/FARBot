import { NextRequest } from "next/server";
import { reviewPackage } from "@/lib/review";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 120;

// POST { text: string, agency?: string } -> blended solicitation review.
// Upload → infer issue areas → retrieve governing FAR (Bedrock + graph) →
// layer agency deviations → suggest the questions the CO should be asking.
export async function POST(req: NextRequest) {
  let body: { text?: string; agency?: string };
  try {
    body = await req.json();
  } catch {
    return Response.json({ error: "invalid JSON body" }, { status: 400 });
  }
  const text = (body.text ?? "").trim();
  if (!text) {
    return Response.json({ error: "missing 'text'" }, { status: 400 });
  }
  if (!process.env.FAR_KB_ID) {
    return Response.json({ error: "Knowledge Base not configured" }, { status: 503 });
  }
  try {
    const result = await reviewPackage(text, body.agency);
    return Response.json(result);
  } catch (err) {
    return Response.json(
      { error: err instanceof Error ? err.message : "review failed" },
      { status: 500 },
    );
  }
}
