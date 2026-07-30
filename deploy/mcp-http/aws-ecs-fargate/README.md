# AWS Hosted MCP Reference

The checked-in CloudFormation file is mechanically inert. The historical design
for ECS Fargate, HTTPS load balancing, and durable EFS state remains available
in version control. Hosted AWS MCP is not supported in v2.40.

Fargate, the load balancer, EFS, CloudWatch, networking, certificates, and
related services can create charges outside Deepr's cost ledger. The scoped MCP
key budget controls only admitted tool work. It does not cap infrastructure
charges, and AWS budget alerts are not hard stops.

The repository performs static local validation only. It does not provide or
endorse a provisioning command. Do not create this stack when relying on
Deepr's `$5` guarantee.

The historical design captured these intended properties:

- Provider credentials are absent by default.
- Desired and minimum task counts begin at zero.
- EFS holds expert state, scoped keys, ledgers, and audit records.
- HTTPS ingress and bounded request concurrency are explicit.
- Scoped keys start read-only with a zero-dollar tool budget.

Before any future hosted release, satisfy the acceptance gate in
[../../README.md](../../README.md), including an enforceable account-level total
cost ceiling and verified residual-resource teardown.
