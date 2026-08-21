---
type: BigQuery Table
title: Customer Orders
description: One row per completed customer order.
tags: [sales, orders]
generated: { by: process:deepr-fixture, at: 2026-08-20T12:00:00Z }
verified: { by: process:fixture-review, at: 2026-08-20T13:00:00Z }
stale_after: 2027-08-20T00:00:00Z
sources:
  - id: orders-contract
    resource: https://example.test/orders-contract
    last_modified: 2026-08-19T23:30:00-04:00
usage_window: { from: 2026-08-01T00:00:00Z, to: 2026-08-20T23:59:59+00:00 }
fixture_extension:
  preserved: true
---
# Orders

Each row represents one completed order.[^orders-contract]

This deliberately broken [future link](future.md) remains consumable.

[^orders-contract]: Orders contract
