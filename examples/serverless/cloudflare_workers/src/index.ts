/**
 * Cloudflare Worker for Glean Connector Execution
 *
 * This worker demonstrates two approaches:
 * 1. Lightweight orchestrator - Triggers a backend service running the Python connector
 * 2. Direct API calls - For simple connectors, make Glean API calls directly
 *
 * For complex connectors with large datasets, use approach #1.
 * For simple connectors with small datasets, approach #2 works well.
 */

export interface Env {
  // Glean configuration
  GLEAN_INSTANCE: string;
  GLEAN_INDEXING_API_TOKEN: string;

  // Connector backend URL (for orchestrator approach)
  CONNECTOR_API_URL?: string;

  // Environment
  ENVIRONMENT: string;
}

interface IndexingResult {
  status: "completed" | "error";
  mode: "FULL" | "INCREMENTAL";
  documentsIndexed?: number;
  error?: string;
  timestamp: string;
}

/**
 * Determine indexing mode based on the scheduled trigger time.
 *
 * This function is called by handleScheduled() when cron triggers fire.
 * The cron schedule is configured in wrangler.toml:
 *   - "0 2 * * *" triggers at 2 AM UTC -> FULL sync
 *   - "0 * * * *" triggers every hour -> INCREMENTAL sync (except 2 AM)
 */
function getIndexingMode(scheduledTime: Date): "FULL" | "INCREMENTAL" {
  const hour = scheduledTime.getUTCHours();
  return hour === 2 ? "FULL" : "INCREMENTAL";
}

/**
 * Approach 1: Trigger a backend service running the Python connector
 *
 * This is recommended for:
 * - Large datasets
 * - Complex transformations
 * - Connectors that need the full SDK capabilities
 */
async function triggerConnectorBackend(
  env: Env,
  mode: "FULL" | "INCREMENTAL"
): Promise<IndexingResult> {
  if (!env.CONNECTOR_API_URL) {
    throw new Error("CONNECTOR_API_URL not configured");
  }

  const response = await fetch(`${env.CONNECTOR_API_URL}/index`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      mode,
      glean_instance: env.GLEAN_INSTANCE,
    }),
  });

  if (!response.ok) {
    throw new Error(`Backend returned ${response.status}: ${await response.text()}`);
  }

  return await response.json();
}

/**
 * Approach 2: Make Glean API calls directly from the Worker
 *
 * This is suitable for:
 * - Simple connectors with small datasets
 * - When the source data is accessible via HTTP
 * - Quick proof-of-concept implementations
 *
 * Note: This is a simplified example. In production, you would
 * implement the full document transformation logic.
 */
async function indexDirectly(
  env: Env,
  mode: "FULL" | "INCREMENTAL"
): Promise<IndexingResult> {
  const gleanApiUrl = `https://${env.GLEAN_INSTANCE}-be.glean.com/api/index/v1`;

  // Example: Index a simple document
  // In production, you would fetch from your source and transform
  const documents = [
    {
      id: "worker-doc-001",
      title: "Document indexed from Cloudflare Worker",
      datasource: "worker_example",
      viewUrl: "https://example.com/doc/001",
      body: {
        mimeType: "text/plain",
        textContent: "This document was indexed directly from a Cloudflare Worker.",
      },
      updatedAt: Math.floor(Date.now() / 1000),
    },
  ];

  // Upload documents to Glean
  const response = await fetch(`${gleanApiUrl}/bulkindexdocuments`, {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${env.GLEAN_INDEXING_API_TOKEN}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      uploadId: `worker-${Date.now()}`,
      datasource: "worker_example",
      documents,
      isFirstPage: true,
      isLastPage: true,
    }),
  });

  if (!response.ok) {
    throw new Error(`Glean API returned ${response.status}: ${await response.text()}`);
  }

  return {
    status: "completed",
    mode,
    documentsIndexed: documents.length,
    timestamp: new Date().toISOString(),
  };
}

/**
 * Handle scheduled (cron) events
 */
async function handleScheduled(
  event: ScheduledEvent,
  env: Env,
  ctx: ExecutionContext
): Promise<void> {
  const scheduledTime = new Date(event.scheduledTime);
  const mode = getIndexingMode(scheduledTime);

  console.log(`Scheduled execution triggered at ${scheduledTime.toISOString()}`);
  console.log(`Indexing mode: ${mode}`);

  try {
    let result: IndexingResult;

    // Use backend approach if configured, otherwise index directly
    if (env.CONNECTOR_API_URL) {
      result = await triggerConnectorBackend(env, mode);
    } else {
      result = await indexDirectly(env, mode);
    }

    console.log(`Indexing completed:`, result);
  } catch (error) {
    console.error(`Indexing failed:`, error);
    throw error; // Re-throw to mark the execution as failed
  }
}

/**
 * Handle HTTP requests (for manual triggers and health checks)
 */
async function handleFetch(
  request: Request,
  env: Env,
  ctx: ExecutionContext
): Promise<Response> {
  const url = new URL(request.url);

  // Health check endpoint
  if (url.pathname === "/health") {
    return new Response(JSON.stringify({ status: "ok" }), {
      headers: { "Content-Type": "application/json" },
    });
  }

  // Manual trigger endpoint
  if (url.pathname === "/trigger" && request.method === "POST") {
    let body: { mode?: string };
    try {
      const parsed = await request.json();
      body = typeof parsed === "object" && parsed !== null ? parsed : {};
    } catch {
      return new Response(
        JSON.stringify({ status: "error", error: "Invalid JSON body" }),
        { status: 400, headers: { "Content-Type": "application/json" } }
      );
    }

    const mode: "FULL" | "INCREMENTAL" = body.mode === "INCREMENTAL" ? "INCREMENTAL" : "FULL";

    try {
      let result: IndexingResult;

      if (env.CONNECTOR_API_URL) {
        result = await triggerConnectorBackend(env, mode);
      } else {
        result = await indexDirectly(env, mode);
      }

      return new Response(JSON.stringify(result), {
        headers: { "Content-Type": "application/json" },
      });
    } catch (error) {
      return new Response(
        JSON.stringify({
          status: "error",
          error: error instanceof Error ? error.message : "Unknown error",
        }),
        {
          status: 500,
          headers: { "Content-Type": "application/json" },
        }
      );
    }
  }

  return new Response("Not Found", { status: 404 });
}

export default {
  fetch: handleFetch,
  scheduled: handleScheduled,
};
