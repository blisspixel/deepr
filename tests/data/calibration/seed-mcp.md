# Model Context Protocol: adoption and surface

The Model Context Protocol (MCP) is an open protocol for connecting AI
applications to external tools and data sources. It defines a client-server
architecture in which a host application runs one or more MCP clients, each
connected to an MCP server that exposes tools, resources, and prompts.

MCP servers commonly communicate over two transports: stdio for local
subprocess servers, and HTTP-based transports for remote servers. The protocol
specifies a capability-negotiation handshake during initialization, so a client
discovers which features (tools, resources, prompts, sampling) a server offers.

Adoption has grown across multiple AI coding and agent platforms, with several
major vendors shipping MCP client support. It is widely believed that MCP will
become the dominant standard for agent-tool interoperability within a year,
though competing approaches remain. Some observers speculate that nearly every
enterprise agent deployment will rely on MCP by 2027, but this is uncertain.

A typical integration exposes domain capabilities as tools with JSON-schema
inputs, and returns structured results the host model can reason over. Servers
may also expose resources (read-only context) and reusable prompt templates.
