# GCP Cloud Run Hosted MCP Template

This template runs the hosted MCP HTTP container on GCP Cloud Run. It mounts a
Cloud Storage bucket at `/data` with Cloud Storage FUSE so expert state, reports,
scoped keys, cost ledgers, and remote-call audit logs survive revision restarts.

It is a local deployment artifact only. Creating GCP resources can incur cloud
costs, so this repo validates the template shape locally and does not run
`gcloud` or `terraform apply` during tests.

## What It Creates

- Cloud Run service running `deepr mcp serve --http --host 0.0.0.0 --path /mcp`.
- Cloud Storage bucket mounted at `/data`.
- Service account with write access to that bucket.
- Optional public `roles/run.invoker` grant controlled by `allow_public_invoker`.
- Single-writer defaults: `max_instances=1` and `max_concurrent_requests=1`.

Provider API keys are intentionally absent. Add provider credentials only when a
scoped key mode, budget ceiling, and rate limit intentionally allow paid tools.

## Storage Semantics

Cloud Storage FUSE is durable but object-backed. It is not a transactional
shared filesystem. This template keeps one Cloud Run instance and one in-process
MCP POST at a time by default so `security/mcp_keys.json` and
`security/mcp_remote_audit.jsonl` remain single-writer files.

Do not raise `max_instances` or `max_concurrent_requests` while keys and audit
state live on this mount. If you need scale-out, move scoped-key and audit state
to a writer-safe store first, then update the template and tests together.

## Build And Push The Image

Build the existing hosted MCP image from the repo root and push it to Artifact
Registry:

```bash
docker build -f deploy/mcp-http/Dockerfile -t REGION-docker.pkg.dev/PROJECT/REPO/deepr-mcp-http:TAG .
docker push REGION-docker.pkg.dev/PROJECT/REPO/deepr-mcp-http:TAG
```

## Bootstrap Scoped Keys

Scoped keys are the production path because they carry mode, expert allowlist,
budget ceiling, rate limit, revocation state, and audit metadata.

Create the key store locally with the same image:

```bash
mkdir -p ./deepr-mcp-data/security
docker run --rm \
  -v "$PWD/deepr-mcp-data:/data" \
  REGION-docker.pkg.dev/PROJECT/REPO/deepr-mcp-http:TAG \
  mcp keys create \
  --mode read_only \
  --rate-limit 30 \
  --budget 0 \
  --keys-path /data/security/mcp_keys.json
```

The key secret is printed once. Store it in the remote agent host secret store.
After Terraform creates the bucket, copy the key store into the bucket before
allowing public invocation:

```bash
gcloud storage cp deepr-mcp-data/security/mcp_keys.json \
  gs://DEEPR_MCP_DATA_BUCKET/security/mcp_keys.json
```

## Deploy

Start with public invocation disabled:

```bash
terraform -chdir=deploy/mcp-http/gcp-cloud-run init
terraform -chdir=deploy/mcp-http/gcp-cloud-run apply \
  -var="project_id=PROJECT" \
  -var="container_image=REGION-docker.pkg.dev/PROJECT/REPO/deepr-mcp-http:TAG" \
  -var="allow_public_invoker=false"
```

Copy `security/mcp_keys.json` into the output bucket, then apply again with
public invocation enabled when the endpoint is ready for remote hosts:

```bash
terraform -chdir=deploy/mcp-http/gcp-cloud-run apply \
  -var="project_id=PROJECT" \
  -var="container_image=REGION-docker.pkg.dev/PROJECT/REPO/deepr-mcp-http:TAG" \
  -var="allow_public_invoker=true"
```

Use an external HTTPS load balancer plus Cloud Armor if you need IP allowlists
or edge rules in front of the Cloud Run URL.

## Validate

After the service is healthy:

```bash
MCP_ENDPOINT="$(terraform -chdir=deploy/mcp-http/gcp-cloud-run output -raw mcp_endpoint)"

deepr mcp smoke-http "$MCP_ENDPOINT" --auth-token "$DEEPR_MCP_KEY"
deepr mcp registration-manifest "$MCP_ENDPOINT" \
  --auth-token "$DEEPR_MCP_KEY" \
  --agent-name planner \
  --output mcp-registration.json
```

The smoke command performs only `$0` structural checks: health, initialize,
tools/list, and free `deepr_tool_search` dispatch.
The registration manifest uses the published
`deepr-mcp-registration-manifest-v1` schema and does not include the key secret.

## Operate

Remote calls through scoped keys append audit records to
`/data/security/mcp_remote_audit.jsonl`, backed by the mounted bucket. Review the
file before widening key mode or budget:

```bash
gcloud storage cp gs://DEEPR_MCP_DATA_BUCKET/security/mcp_remote_audit.jsonl ./mcp_remote_audit.jsonl
deepr mcp audit list --audit-path ./mcp_remote_audit.jsonl --limit 50
deepr mcp audit summary --audit-path ./mcp_remote_audit.jsonl
```

Keep the same guardrails as the local container recipe:

- Use one scoped key per remote agent.
- Start read-only with `--budget 0`.
- Set a per-key rate limit.
- Keep the single-writer defaults unless key and audit storage move.
- Back up the mounted bucket and remote audit log.
- Add provider API keys only when paid tools are intentional.
