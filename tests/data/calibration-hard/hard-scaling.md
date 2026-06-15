# Scaling and bottleneck review

The service currently sustains about 4,000 requests per second on the existing
three-node cluster during peak hours, measured over the last two weeks.

For years the team assumed the bottleneck was CPU, and capacity planning was
built around adding cores. Profiling this quarter showed that assumption was
wrong: the limiter is network I/O between the app tier and the database, not
CPU. The CPU-bound story should not be repeated.

If horizontal sharding were introduced, throughput could in principle increase
several-fold. That number is a back-of-envelope guess only; no sharding work has
been started and the estimate has not been validated against a prototype, so it
should not be quoted as a result.

What is confirmed: enabling connection pooling reduced p99 latency from 240ms to
180ms in a controlled before/after test on the staging cluster. That change is
already in production.

A vendor suggested their managed cache would "eliminate the database bottleneck
entirely." We have not evaluated it and make no claim about that.
