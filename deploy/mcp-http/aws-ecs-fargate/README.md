# AWS ECS Fargate Hosted MCP Template

This template runs the hosted MCP HTTP container on AWS ECS Fargate behind an
HTTPS Application Load Balancer. It mounts EFS at `/data` so expert state,
reports, scoped keys, cost ledgers, and remote-call audit logs survive task
restarts.

It is a local deployment artifact only. Creating AWS resources can incur cloud
costs, so this repo validates the template shape locally and does not run `aws`
commands during tests.

## What It Creates

- ECS cluster, Fargate task definition, and ECS service.
- Internet-facing Application Load Balancer with an HTTPS listener on port 443.
- EFS file system, mount targets, and an access point mounted at `/data`.
- Security groups that allow only HTTPS to the load balancer, MCP HTTP from the
  load balancer to tasks, and NFS from tasks to EFS.
- CloudWatch logs for the hosted MCP container.
- CPU autoscaling with a default 0 to 3 task range.
- A `MaxConcurrentRequests` parameter wired to both
  `DEEPR_MCP_HTTP_MAX_CONCURRENCY` and `deepr mcp serve --max-concurrency`.

Provider API keys are intentionally absent. Add provider credentials only when a
scoped key mode, budget ceiling, and rate limit intentionally allow paid tools.

## Build And Push The Image

Build the existing hosted MCP image from the repo root and push it to a registry
your Fargate task can pull from:

```bash
docker build -f deploy/mcp-http/Dockerfile -t ACCOUNT.dkr.ecr.REGION.amazonaws.com/deepr-mcp-http:TAG .
docker push ACCOUNT.dkr.ecr.REGION.amazonaws.com/deepr-mcp-http:TAG
```

Public registries can work too, provided the task subnets have outbound HTTPS.
For private task subnets, use NAT or VPC endpoints for the registry and AWS APIs
needed by Fargate.

## Bootstrap Scoped Keys

Scoped keys are the production path because they carry mode, expert allowlist,
budget ceiling, rate limit, revocation state, and audit metadata. EFS must
contain `security/mcp_keys.json` before a public-bind task can start without a
bootstrap shared token.

Create the key store locally with the same image:

```bash
mkdir -p ./deepr-mcp-data/security
docker run --rm \
  -v "$PWD/deepr-mcp-data:/data" \
  ACCOUNT.dkr.ecr.REGION.amazonaws.com/deepr-mcp-http:TAG \
  mcp keys create \
  --mode read_only \
  --rate-limit 30 \
  --budget 0 \
  --keys-path /data/security/mcp_keys.json
```

The key secret is printed once. Store it in the remote agent host secret store.
Copy `deepr-mcp-data/security/mcp_keys.json` onto the EFS access point path
before scaling the ECS service above zero, or pass `InitialSharedAuthToken` for
the first boot only and remove it after scoped keys are present.

## Deploy

The template expects an existing VPC, two load-balancer subnets, two task/EFS
subnets, and an ACM certificate in the same region as the load balancer.

```bash
aws cloudformation deploy \
  --stack-name deepr-mcp-http \
  --template-file deploy/mcp-http/aws-ecs-fargate/template.yaml \
  --capabilities CAPABILITY_IAM \
  --parameter-overrides \
    ContainerImage=ACCOUNT.dkr.ecr.REGION.amazonaws.com/deepr-mcp-http:TAG \
    VpcId=vpc-00000000000000000 \
    PublicSubnetIdA=subnet-11111111111111111 \
    PublicSubnetIdB=subnet-22222222222222222 \
    TaskSubnetIdA=subnet-33333333333333333 \
    TaskSubnetIdB=subnet-44444444444444444 \
    CertificateArn=arn:aws:acm:REGION:ACCOUNT:certificate/CERT-ID \
    AllowedIngressCidr=203.0.113.0/24 \
    DesiredCount=0 \
    MinTasks=0 \
    MaxTasks=3 \
    MaxConcurrentRequests=32
```

Keep `DesiredCount=0` until either the EFS key store is populated or
`InitialSharedAuthToken` is set. Keep `AllowedIngressCidr` restricted to the
remote agent host egress range when it is known. After the scoped-key file is on
EFS, update the stack with `DesiredCount=1` and `MinTasks=1`.

## Validate

After the service is healthy and DNS points at the load balancer:

```bash
deepr mcp smoke-http https://mcp.example.com/mcp --auth-token "$DEEPR_MCP_KEY"
deepr mcp registration-manifest https://mcp.example.com/mcp \
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
`/data/security/mcp_remote_audit.jsonl`. Review the file before widening key
mode or budget:

```bash
deepr mcp audit list --audit-path ./mcp_remote_audit.jsonl --limit 50
deepr mcp audit summary --audit-path ./mcp_remote_audit.jsonl
```

Keep the same guardrails as the local container recipe:

- Use one scoped key per remote agent.
- Start read-only with `--budget 0`.
- Set a per-key rate limit.
- Keep `MaxConcurrentRequests` bounded.
- Back up the EFS file system and remote audit log.
- Add provider API keys only when paid tools are intentional.
