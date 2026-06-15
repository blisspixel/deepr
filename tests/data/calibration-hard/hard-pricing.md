# Cost analysis (read the caveats)

The provider's list price is $2.00 per million input tokens and $8.00 per million
output tokens on the standard tier, as published on their pricing page.

A widely shared social-media estimate put the all-in cost at about $0.001 per
query. That estimate counted only input tokens and ignored output tokens, retries,
and tool calls, so it understates real cost substantially. It should not be used;
our own measured average is closer to $0.012 per query on representative traffic.

Some commentators expect token prices to halve within a year. There is no
announced price change from the provider, and past cadence is an unreliable guide,
so this is speculation, not a basis for planning.

A large-context surcharge does apply: prompts over 200K tokens are billed at
roughly double the base input rate, which is confirmed in the provider's docs.

Annual spend at current volume is about $43,000 based on the measured per-query
cost and last quarter's request counts; this is an extrapolation, not a contract.
