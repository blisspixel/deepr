# Azure Research Service Reference

This directory contains an inert placeholder plus legacy handler source for
architecture review. It is not a supported deployment surface in the current release. The
deployable template remains available only in version control history.

The historical design included Container Apps, Functions, storage,
queues, Cosmos DB, networking, monitoring, and key management. Those resources
can incur charges without any model call. Deepr's provider budget and cost
ledger cannot cap the Azure subscription total, and Azure Cost Management
budgets are alerts rather than hard stops.

`deploy.sh` and `scripts/setup_azure.py` exit before Azure authentication or
provisioning. The hosted API independently rejects paid research before payload
parsing, durable writes, queueing, or provider construction. Supplying
credentials does not remove these blocks.

The checked-in files may be used for:

- Static security and architecture review.
- Reviewing the deliberately invalid Bicep target scope.
- Planning a future zero-idle-cost design with an account-level hard ceiling.
- Planning an operator-controlled cleanup through the Azure portal.

Do not create Azure resources from this reference when relying on Deepr's `$5`
guarantee. See [../README.md](../README.md) for the hosted acceptance gate.
