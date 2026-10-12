# Core YAML runtime on supported Python versions

Status: corrective implementation, 2026-10-11.

The actual v2.50.25 public Bash installer successfully installed a core wheel
on ordinary CPython 3.13, but `doctor --skip-connectivity` then failed its
required MCP capability check because `yaml` was missing. The declared
Python-3.13 dependency, PyYAML-ft 8, intentionally provides `yaml_ft` instead.
The existing YAML import owners need canonical `yaml`, including its events.
Full development installs mask this mismatch with another PyYAML dependency;
the dedicated core-install job currently checks only Python 3.12.

Use `PyYAML>=6.0.3,<7.0.0` for every supported ordinary stable Python minor.
Its published native wheels cover 3.12, 3.13 and 3.14. Remove the direct fork
requirement, preserving any independent development-tool dependency on it.
Keep the existing safe parsers and public imports unchanged. Global aliases,
eight separate import shims, an old fork version, and installing full extras
would add compatibility paths or hide the core dependency defect.

Extend the existing core-install CI job to 3.12, 3.13 and 3.14, retaining its
current commands, tooling pins and floors. Check real MCP conformance, nested
YAML frontmatter, unsafe-tag refusal and both YAML configuration loaders in a
core environment. Qualify fresh unpinned wheel installs with provider network
access blocked, including the managed 3.13 path used by the public installer.
Free-threaded 3.14 remains experimental under the existing promotion gates.

This is a compatible dependency and packaging correction for 2.50.26. It adds
no spend, mutation, provider or remote-control authority. Published 2.50.25
tag and asset bytes remain unchanged, and its failed public acceptance remains
retained. Rollback to 2.50.24 would retain the same dependency/import mismatch.

Primary references:

- [PyYAML 6.0.3 metadata and native wheels](https://pypi.org/pypi/PyYAML/6.0.3/json)
- [PyYAML 6.0.3 release](https://github.com/yaml/pyyaml/releases/tag/6.0.3)
- [PyYAML-ft 8 namespace change](https://github.com/Quansight-Labs/pyyaml-ft/blob/v8.0.0/CHANGES)
- [Fork import API and scope](https://github.com/Quansight-Labs/pyyaml-ft/blob/v8.0.0/README.md)
