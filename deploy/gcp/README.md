# GCP Research Service Reference

This directory contains an inert placeholder plus legacy handler source for
architecture review. It is not a supported deployment surface in v2.40. The
deployable template remains available only in version control history.

The historical design included Cloud Run, Cloud Functions, Pub/Sub,
storage, networking, monitoring, and secret management. Those resources can
incur charges without any model call. Deepr's provider budget and cost ledger
cannot cap the Cloud Billing account total, and GCP budgets are alerts rather
than hard stops.

`deploy.sh` exits before GCP authentication or Terraform operations. The hosted
API independently rejects paid research before payload parsing, durable writes,
queueing, or provider construction. Supplying credentials does not remove
these blocks.

The checked-in files may be used for:

- Static security and architecture review.
- Reviewing the impossible Terraform version constraint.
- Planning a future zero-idle-cost design with an account-level hard ceiling.
- Planning an operator-controlled cleanup through the GCP console.

Do not create GCP resources from this reference when relying on Deepr's `$5`
guarantee. See [../README.md](../README.md) for the hosted acceptance gate.
