const MCP_PATH_PREFIX = "/mcp";
const MAX_BODY_BYTES = 1048576;

const HOP_BY_HOP_HEADERS = new Set([
  "connection",
  "keep-alive",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailer",
  "transfer-encoding",
  "upgrade",
]);

export default {
  async fetch(request, env) {
    const requestUrl = new URL(request.url);
    if (!isMcpPath(requestUrl.pathname)) {
      return jsonError(404, "NOT_FOUND", "Only /mcp endpoints are proxied.");
    }

    const origin = parseOrigin(env);
    if (origin.error) {
      return origin.error;
    }

    const body = await readBoundedBody(request);
    if (body.error) {
      return body.error;
    }

    const targetUrl = buildTargetUrl(origin.url, requestUrl);
    const headers = proxiedHeaders(request, requestUrl);
    const init = {
      method: request.method,
      headers,
      redirect: "manual",
    };

    if (body.value !== undefined) {
      init.body = body.value;
    }

    return fetch(new Request(targetUrl, init));
  },
};

function isMcpPath(pathname) {
  return pathname === MCP_PATH_PREFIX || pathname.startsWith(`${MCP_PATH_PREFIX}/`);
}

function parseOrigin(env) {
  const rawOrigin = env.DEEPR_MCP_ORIGIN;
  if (!rawOrigin) {
    return {
      error: jsonError(500, "ORIGIN_NOT_CONFIGURED", "DEEPR_MCP_ORIGIN is required."),
    };
  }

  let url;
  try {
    url = new URL(rawOrigin);
  } catch {
    return {
      error: jsonError(500, "ORIGIN_INVALID", "DEEPR_MCP_ORIGIN must be a valid URL."),
    };
  }

  if (url.protocol !== "https:") {
    return {
      error: jsonError(500, "ORIGIN_REQUIRES_HTTPS", "DEEPR_MCP_ORIGIN must use https."),
    };
  }

  return { url };
}

async function readBoundedBody(request) {
  if (request.method === "GET" || request.method === "HEAD") {
    return {};
  }

  const contentLength = request.headers.get("Content-Length");
  if (contentLength !== null) {
    const declaredLength = Number(contentLength);
    if (!Number.isSafeInteger(declaredLength) || declaredLength < 0) {
      return {
        error: jsonError(400, "CONTENT_LENGTH_INVALID", "Content-Length must be a non-negative integer."),
      };
    }
    if (declaredLength > MAX_BODY_BYTES) {
      return {
        error: jsonError(413, "REQUEST_TOO_LARGE", "MCP request body exceeds 1 MiB."),
      };
    }
  }

  if (request.body === null) {
    return { value: new ArrayBuffer(0) };
  }

  const reader = request.body.getReader();
  const chunks = [];
  let totalBytes = 0;
  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      break;
    }
    totalBytes += value.byteLength;
    if (totalBytes > MAX_BODY_BYTES) {
      await reader.cancel("request body limit exceeded");
      return {
        error: jsonError(413, "REQUEST_TOO_LARGE", "MCP request body exceeds 1 MiB."),
      };
    }
    chunks.push(value);
  }

  const body = new Uint8Array(totalBytes);
  let offset = 0;
  for (const chunk of chunks) {
    body.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return { value: body.buffer };
}

function buildTargetUrl(originUrl, requestUrl) {
  const targetUrl = new URL(originUrl.toString());
  const basePath = originUrl.pathname.replace(/\/+$/, "");
  const suffix =
    requestUrl.pathname === MCP_PATH_PREFIX ? "" : requestUrl.pathname.slice(MCP_PATH_PREFIX.length);

  targetUrl.pathname = `${basePath}${suffix}` || "/";
  targetUrl.search = requestUrl.search;
  return targetUrl.toString();
}

function proxiedHeaders(request, requestUrl) {
  const headers = new Headers();

  for (const [key, value] of request.headers) {
    const normalized = key.toLowerCase();
    if (normalized === "host" || HOP_BY_HOP_HEADERS.has(normalized)) {
      continue;
    }
    headers.set(key, value);
  }

  headers.set("X-Forwarded-Proto", "https");
  headers.set("X-Forwarded-Host", requestUrl.host);

  const cfClientIp = request.headers.get("CF-Connecting-IP");
  const forwardedFor = request.headers.get("X-Forwarded-For");
  if (cfClientIp) {
    headers.set("X-Forwarded-For", forwardedFor ? `${forwardedFor}, ${cfClientIp}` : cfClientIp);
  }

  return headers;
}

function jsonError(status, code, message) {
  return new Response(JSON.stringify({ error: { code, message } }), {
    status,
    headers: {
      "Cache-Control": "no-store",
      "Content-Type": "application/json; charset=utf-8",
    },
  });
}
