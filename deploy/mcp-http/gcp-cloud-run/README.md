# GCP Hosted MCP Reference

The checked-in Terraform file has an impossible version constraint and is
mechanically inert. The historical Cloud Run design remains available in
version control. Hosted GCP MCP is not supported in the current release.

Cloud Run, Cloud Storage, build, logging, networking, and related services can
create charges outside Deepr's cost ledger. The scoped MCP key budget controls
only admitted tool work. It does not cap Cloud Billing charges, and GCP budgets
are not hard stops.

The repository performs static local validation only. It does not provide or
endorse a Terraform apply command. Do not create these resources when relying
on Deepr's `$5` guarantee.

The historical design captured these intended properties:

- Provider credentials are absent by default.
- Public invocation is disabled by default.
- Instance and request concurrency begin at one for single-writer state.
- The mounted bucket holds expert state, scoped keys, ledgers, and audits.
- Scoped keys start read-only with a zero-dollar tool budget.

Before any future hosted release, satisfy the acceptance gate in
[../../README.md](../../README.md), including an enforceable account-level total
cost ceiling and verified residual-resource teardown.
