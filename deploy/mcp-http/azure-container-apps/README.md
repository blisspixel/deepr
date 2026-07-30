# Azure Hosted MCP Reference

The checked-in Bicep file is deliberately invalid and mechanically inert. The
historical Container Apps and Azure Files design remains available in version
control. Hosted Azure MCP is not supported in v2.40.

Container Apps, storage, Log Analytics, networking, and related services can
create charges outside Deepr's cost ledger. The scoped MCP key budget controls
only admitted tool work. It does not cap Azure infrastructure charges, and
Azure Cost Management budgets are not hard stops.

The repository performs static local validation only. It does not provide or
endorse a provisioning command. Do not create these resources when relying on
Deepr's `$5` guarantee.

The historical design captured these intended properties:

- Provider credentials are absent by default.
- Azure Files holds expert state, scoped keys, ledgers, and audit records.
- HTTPS ingress and bounded request concurrency are explicit.
- Public ingress can be disabled and CIDR restrictions are modeled.
- Scoped keys start read-only with a zero-dollar tool budget.

Before any future hosted release, satisfy the acceptance gate in
[../../README.md](../../README.md), including an enforceable account-level total
cost ceiling and verified residual-resource teardown.
