---
type: BigQuery Table
title: Customer Orders
description: One row per completed customer order.
tags: [sales, orders]
generated: { by: process:deepr-fixture, at: 2026-08-20T12:00:00Z }
verified: { by: process:fixture-review, at: 2026-08-20T13:00:00Z }
sources:
  - id: orders-contract
    resource: https://example.test/orders-contract
fixture_extension:
  preserved: true
---
# Orders

Each row represents one completed order.[^orders-contract]

This deliberately broken [future link](future.md) remains consumable.

[^orders-contract]: Orders contract
