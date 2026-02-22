import { Context } from "hono";
import { Env, getSupabase } from "../lib/supabase";

const SMOKE_PNG_B64 =
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==";

function decodeBase64ToBytes(value: string): Uint8Array {
  return Uint8Array.from(atob(value), (char) => char.charCodeAt(0));
}

export const smokeHandler = async (c: Context<{ Bindings: Env }>) => {
  const supabase = getSupabase(c.env);
  const startedAt = Date.now();
  let runId: string | null = null;

  try {
    const { data: run, error: runError } = await supabase
      .from("runs")
      .insert({ status: "running", prompt: "smoke-cloud-dust" })
      .select()
      .single();
    if (runError) throw runError;
    runId = run.id;

    const artifactPath = `artifacts/${runId}/smoke.png`;
    const smokeBytes = decodeBase64ToBytes(SMOKE_PNG_B64);
    const { error: uploadError } = await supabase.storage
      .from("artifacts")
      .upload(artifactPath, smokeBytes, {
        contentType: "image/png",
        upsert: true,
      });
    if (uploadError) throw uploadError;

    const { error: updateError } = await supabase
      .from("runs")
      .update({
        status: "success",
        artifacts: {
          smoke_png: artifactPath,
          orchestration_stack: ["playwright", "dust", "gemini", "lovable"],
        },
        error: null,
      })
      .eq("id", runId);
    if (updateError) throw updateError;

    return c.json({
      run_id: runId,
      status: "success",
      artifacts: { smoke_png: artifactPath },
      elapsed_ms: Date.now() - startedAt,
    });
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : String(err);
    if (runId) {
      await supabase.from("runs").update({ status: "error", error: message }).eq("id", runId);
    }
    return c.json(
      { status: "error", error: message, elapsed_ms: Date.now() - startedAt },
      500,
    );
  }
};
