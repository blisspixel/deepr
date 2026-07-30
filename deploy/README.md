# Deployment References

Deepr v2.40 is CLI and local first. The files under `deploy/` are architecture
references and local validation fixtures. They are not a supported cloud
deployment surface.

## Cost boundary

AWS, Azure, GCP, Cloudflare, hosted load balancers, managed storage, logging,
queues, and network services can create charges outside Deepr's cost ledger.
Cloud budget alerts notify after usage and do not enforce a hard total. Deepr
therefore cannot guarantee the repository's `$5` ceiling for these resources.

The legacy deploy, validate, destroy, and setup scripts fail closed before
authentication or cloud operations. The checked-in templates are mechanically
inert markers. Deployable historical designs remain in version control only.
No provider key turns them into a supported execution path.

## Supported local shape

The local container recipe in [mcp-http/](mcp-http/) can run Deepr's inbound
MCP server on the operator's machine. Start with scoped keys, read-only mode,
and a zero-dollar key budget. An external MCP host may call that inbound
server. Deepr's own outbound remote-client, smoke, and validation commands are
quarantined before network access because endpoint self-reporting cannot prove
cost.

## Reference inventory

| Path | Purpose | Execution status |
|---|---|---|
| `aws/` | SAM and CloudFormation research-service design | Reference only |
| `azure/` | Bicep research-service design | Reference only |
| `gcp/` | Terraform research-service design | Reference only |
| `mcp-http/` | Local container plus hosted MCP design variants | Local container supported; cloud variants reference only |
| `shared/` | Shared validation and response helpers | Local tests only |

The hosted research handlers independently reject submission before request
parsing, job writes, queue writes, or provider construction. They do not solve
cloud infrastructure billing.

## Future hosted acceptance gate

A cloud deployment is not supportable until all of the following are proven:

- An account-level mechanism prevents total infrastructure and provider spend
  from exceeding the operator's ceiling.
- Provisioning starts at zero running instances and zero paid network paths.
- Every possible charge source is inventoried with owner and settlement state.
- Provider dispatch uses Deepr's durable estimate, reservation, grant,
  dispatch-marker, usage-settlement, and append-only ledger transaction.
- Cancellation, retries, autoscaling, logs, storage growth, and idle resources
  have hard limits and tested circuit breakers.
- Teardown is independently verified and residual billable resources are
  reported.

Until that gate is met, review the historical designs in version control and
use a cloud provider's cost calculator only in an operator-controlled process
outside Deepr.
