# Model benchmark notes (mixed reliability)

On the MMLU subset used in this evaluation, Model A scored 82% and Model B
scored 79%. Both were run on the same held-out split with identical prompting.

An earlier vendor blog post claimed Model A reached 95% on this benchmark. That
figure came from a run on a contaminated split that overlapped the training
data, and the vendor later retracted it. We do not treat 95% as a real result.

On one internal coding task, Model B finished ahead of Model A. This is a single
task and does not establish that Model B is generally stronger; on the broader
suite Model A leads. We draw no general ranking from the coding result alone.

Preliminary runs of Model C look competitive on easy questions, but the sample
was eight prompts, far too small to conclude anything. Treat Model C as untested
here rather than as a third contender.

Latency, by contrast, was measured carefully: Model A returned a median 1.2
seconds per request and Model B 0.9 seconds, across 500 requests each.
