# Cloudflare MCP Ingress Reference

The checked-in Worker and Wrangler files are mechanically inert. The historical
edge-proxy design remains available in version control. Cloudflare ingress is
not a supported deployment surface in the current release.

Worker requests, routes, logs, DNS, and the origin can create charges outside
Deepr's cost ledger. Those infrastructure charges remain outside Deepr's cost ledger.
An origin-side MCP key budget does not cap Cloudflare or
origin infrastructure charges. Do not deploy this reference when relying on
Deepr's `$5` guarantee.

The historical design captured these intended properties:

- Proxies only `/mcp` paths.
- Requires an HTTPS origin.
- Caps request bodies before forwarding.
- Forwards only the headers needed by the MCP origin.
- Keeps provider credentials, scoped-key state, budgets, and audit data at the
  origin.

The repository does not provide or endorse a Worker deployment command. Before
any future hosted release, satisfy the acceptance gate in
[../../README.md](../../README.md), including an enforceable account-level total
cost ceiling and verified residual-resource teardown.
