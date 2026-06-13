# Cost-aware model routing

Auto-mode routing selects a model per query based on task complexity and a
quality/cost tradeoff. Simple factual lookups can be served by small, cheap
models; complex synthesis and deep research route to stronger, more expensive
models.

Routing quality depends on the data behind it. With measured benchmark
rankings, routing can pick the best model per task type. Without benchmarks,
provisional rankings are used; deriving provisional quality from price alone is
unreliable, because cheap models often perform near frontier on easy tasks.
Published benchmark priors give better provisional routing than price.

A reported figure suggests cost savings of 10-20x from routing simple queries
to budget models instead of always using a flagship, though the exact figure
depends on the query mix. Some claim auto-routing eliminates the need for any
manual model selection, but operators frequently still pin a model for
reproducibility.

The cheapest-capable principle - pick the least expensive model whose measured
quality clears a task's floor - requires both honest quality estimates and a
value-aware selection step, not quality-maximization alone.
