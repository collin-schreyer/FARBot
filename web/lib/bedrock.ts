import { BedrockRuntimeClient, ConverseCommand } from "@aws-sdk/client-bedrock-runtime";

// Shared Bedrock Converse helper for the review pipeline. The main model
// (BEDROCK_MODEL_ARN) is Sonnet; the cheap model (BEDROCK_CHEAP_MODEL_ID) is
// Haiku for the high-volume stages (issue inference, suggestions).
const REGION = process.env.AWS_REGION ?? "us-east-1";
const MAIN = process.env.BEDROCK_MODEL_ARN ?? "";
export const CHEAP_MODEL = process.env.BEDROCK_CHEAP_MODEL_ID || MAIN;

const client = new BedrockRuntimeClient({ region: REGION });

export async function converseText(
  system: string,
  user: string,
  opts: { model?: string; maxTokens?: number; temperature?: number } = {},
): Promise<string> {
  const resp = await client.send(
    new ConverseCommand({
      modelId: opts.model || CHEAP_MODEL,
      system: [{ text: system }],
      messages: [{ role: "user", content: [{ text: user }] }],
      inferenceConfig: {
        maxTokens: opts.maxTokens ?? 1200,
        temperature: opts.temperature ?? 0,
      },
    }),
  );
  return resp.output?.message?.content?.[0]?.text ?? "";
}

// Parse JSON from a model response, tolerating ```json fences / prose wrappers.
export function parseJson<T = unknown>(text: string): T | null {
  if (!text) return null;
  let t = text.trim();
  const fence = t.match(/```(?:json)?\s*\n?([\s\S]*?)\n?\s*```/);
  if (fence) t = fence[1].trim();
  try {
    return JSON.parse(t) as T;
  } catch {
    const obj = t.match(/\{[\s\S]*\}/);
    if (obj) {
      try {
        return JSON.parse(obj[0]) as T;
      } catch {
        /* fall through */
      }
    }
  }
  return null;
}

export async function converseJson<T = unknown>(
  system: string,
  user: string,
  opts: { model?: string; maxTokens?: number; temperature?: number } = {},
): Promise<T | null> {
  const text = await converseText(system, user, { maxTokens: 1500, ...opts });
  return parseJson<T>(text);
}
