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
  if (contentLength !== null && Number(contentLength) > MAX_BODY_BYTES) {
    return {
      error: jsonError(413, "REQUEST_TOO_LARGE", "MCP request body exceeds 1 MiB."),
    };
  }

  const body = await request.arrayBuffer();
  if (body.byteLength > MAX_BODY_BYTES) {
    return {
      error: jsonError(413, "REQUEST_TOO_LARGE", "MCP request body exceeds 1 MiB."),
    };
  }

  return { value: body };
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
