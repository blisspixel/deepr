# Development server debugger boundary

Status: compatible security correction, October 11, 2026.

## Problem

The API module accepts `DEEPR_DEBUG` on loopback. The dashboard module accepts
`FLASK_DEBUG`, and `deepr web` accepts `--debug` after its loopback and
authentication checks. Each reaches a Flask or Flask-SocketIO development
server call. Debug mode enables Werkzeug's browser debugger by default, which
can execute Python independently of application route authentication.

## Decision

Pass `use_debugger=False` explicitly at all three existing server calls. Keep
the operator's debug setting and the framework's existing reload behavior.
The API still restricts debug mode to loopback. The dashboard still refuses
non-loopback development-server binds. Authentication and the separate
tokenless-loopback compatibility opt-ins keep their existing requirements.

This is a deterministic execution boundary, consistent with
[AGENTIC_BALANCE](../plans/AGENTIC_BALANCE.md). It changes no model judgment,
spend authority, persistent format, dependency, or production-server policy.

The official [Flask debugging documentation](https://flask.palletsprojects.com/en/stable/debugging/)
documents disabling the built-in debugger separately from debug mode. The
[Flask-SocketIO server contract](https://flask-socketio.readthedocs.io/en/latest/api.html#flask_socketio.SocketIO.run)
passes server options through to the selected backend. Deepr explicitly selects
its existing threading backend, which forwards this option to Flask.
These contracts were checked October 11, 2026.

## Alternatives rejected

- Forcing `debug=False` would unnecessarily remove explicit development and
  reload behavior. Debug mode and the executable browser debugger are separate
  controls.
- Trusting loopback, route authentication, or the debugger PIN would leave the
  executable middleware enabled. Those controls do not replace disabling it.
- Extracting another startup module would add indirection to three bounded
  framework calls without improving this enforcement boundary.

## Verification

Exercise the actual API module startup, dashboard startup helper, and Click
launcher with the installed frameworks and a mocked final server listener.
Verify that debug and normal launches disable the browser debugger while
retaining their prior reload settings. Cover debug opt-in spellings, loopback
hosts, configured authentication, explicit tokenless compatibility, and existing
unauthenticated or non-loopback refusals. Retain the existing authentication
regressions and run lint, format, file-size, complexity/security, paid-boundary,
and documentation checks. No live listener or model/provider call is needed.
