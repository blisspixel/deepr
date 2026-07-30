# AWS Research Service Reference

This directory contains inert placeholders plus legacy handler source for
architecture review. It is not a supported deployment surface in v2.40. The
deployable template remains available only in version control history.

The historical design included Fargate, load balancing, networking,
storage, queues, monitoring, and key management. Those resources can incur
charges even when no model call occurs. Deepr's provider budget and cost ledger
cannot cap the AWS account total, and AWS budget alerts are not hard stops.

`deploy.sh` exits before AWS authentication, build, or provisioning. The hosted
API and worker also reject paid research before request parsing, durable writes,
queueing, or provider construction. Supplying credentials does not remove
either block.

The checked-in files may be used for:

- Static security and architecture review.
- Reviewing the mechanically inert template marker.
- Planning a future zero-idle-cost design with an account-level hard ceiling.
- Planning an operator-controlled cleanup through the AWS console.

Do not create AWS resources from this reference when relying on Deepr's `$5`
guarantee. See [../README.md](../README.md) for the hosted acceptance gate.
