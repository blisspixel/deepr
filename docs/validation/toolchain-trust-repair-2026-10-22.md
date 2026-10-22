# Installer trust repair, 2026-10-22 (#283)

The source at `e22896a1` selected uv 0.13.0 in eight workflow setup blocks and
three container builds, and pip 26.2.1 in the dev lock. Runtime certifi already
required and selected 2026.10.19. No exploitation, credential disclosure or
compromised artifact was established.

The [uv advisory](https://github.com/astral-sh/uv/security/advisories/GHSA-hq85-5cpj-mr62)
and [Python incident notice](https://discuss.python.org/t/information-for-python-users-regarding-emudhra-emsign-ca-certificate-security-incident/109576)
identify independent installer bundles. The selected
[uv 0.13.5](https://github.com/astral-sh/uv/releases/tag/0.13.5) also updates
managed Python builds; [Python 3.15.1](https://www.python.org/downloads/release/python-3151/)
bundles repaired pip and ensurepip. Package metadata retains Python 3.11-3.15
support and existing compatible licenses.

## Reproduction and repair boundary

Four offline version-policy cases failed on the original source: both workflow
families, the missing dev security floor, and the affected installed pip.
Eight real-shell cases against the original installer scripts also failed the
new old/unknown-tool refusal requirement. All command, network and install
operations in those shell cases were local doubles.

The original native environment used Python 3.15.0, pip 26.2.1, ensurepip 26.2.1
and pip-vendored certifi 2026.06.17. Its vendored bundle contained the affected
`emSign ECC Root CA - G3`; the repaired bundle does not. This was an offline
bundle inspection, not a live interception experiment. A clean pip-audit result
alone does not establish this trust-store property.

The patch pins uv 0.13.5 throughout maintained execution, requires it for uv
project operations and managed public install/upgrade, adds a dev-only
pip>=26.2.2 floor, and updates only pip in the application lock. Application
certifi stays unchanged. The managed default and all container stages advance
to Python 3.15.1. Uninstall, manager ownership and the supported minor versions
remain. Existing pip/pipx environments stay owner-managed and require the
explicit repair described in [installation guidance](../INSTALL.md#installer-trust-repair-2026-10-22).

## Inspected local environments and retained evidence

| Maintained environment | Python | pip | ensurepip | pip-vendored certifi |
| --- | --- | --- | --- | --- |
| Native, recreated | 3.15.1, 2026-10-21 build | 26.2.2 | 26.2.2 | 2026.10.19 |
| Floor, private cold managed directory | 3.11.17, 2026-10-21 build | 26.2.2 | 26.2.2 | 2026.10.19 |

The first floor refresh reused a 2026-10-09 cached interpreter with ensurepip
24.0, despite repairing installed pip. That trial is retained separately;
private cold installation obtained the repaired 2026-10-21 build. The user's
owned uv and uvx executables now report 0.13.5. Old executables/environments
remain quarantined evidence and are not reused for acquisition. This is not a
claim that every environment or cache on this machine was inspected or fixed.

The uv archive matched its official release SHA256 before execution. The pip
wheel hash in the lock matches the Python incident notice. The official
`python:3.15.1-slim` multiarch registry response was checked against digest
`sha256:08275f764e022331c6d3e3ca55d8cce01fa4684b02111adf0445d71806fe7941`.

## Release acceptance

The final focused upgrade and policy checks passed 44 cases. The real-shell
installer checks also passed, including refusal before downloads/mutation,
retained uninstall and unchanged manager ownership. Full unit/coverage,
repository gates, native/floor strict checks and dependency audits are required
on the final candidate. Exact PR and resulting-main CI remain release gates.

Local Docker daemon access is denied. Hosted CI must build all three images
with `--pull --no-cache`, refresh system CA packages in every stage, and inspect
base pip, ensurepip and vendored certifi without network. Existing offline
runtime, compiler-absence and MCP conformance checks remain. Actual hosted and
public-install acceptance is recorded on the matching GitHub release.

No TLS verification was disabled, and no provider API, cloud deployment,
private assignment key or new semantic trial was used. Existing user
installations and deployed images require their owner's explicit refresh.
S0 and the remaining roadmap work are unchanged.
