# Executive Summary

Deepr’s MCP integration must support **two distinct use cases**: (1) exposing **domain experts** (the chat-based knowledge agents) via a tool-style interface, and (2) exposing its **research data corpus** (indexed documents and vector stores) to deep-research and multi-agent workflows. Both use cases are valuable. In practice, start by hardening and extending the expert-chat interface (to ensure stable agent access), **then** add a dedicated search/fetch interface for retrieval by deep-research models. Key recommendations include implementing a proper HTTP/JSON MCP server (instead of raw stdio) with *search* and *fetch* endpoints for deep research, adding streaming and multi-session support, and enforcing robust security (token authentication, access controls). We also outline how to configure Claude Desktop and Cursor to use Deepr’s MCP, and how OpenAI’s deep-research models can call Deepr. Prioritization: high impact items are search+fetch support, native HTTP API with streaming, and security/authentication. Medium impact items include multi-agent context (conversation IDs) and developer convenience features. Low-hanging enhancements (e.g. richer metadata) are lower priority.  

# MCP Use Cases (Architecture Analysis)

**1. Expert-as-a-Tool (Chat Agent):** In this mode, each Deepr *Expert* (e.g. “Salesforce Architect”, “Azure Architect”) acts as a tool that can be queried by another agent. An external LLM (e.g. Claude, GPT-5) communicates with Deepr via MCP calls like `list_experts`, `get_expert_info`, and `query_expert`. The response is a scored answer with citations from Deepr’s knowledge base. This is essentially a **question-answering chat** interface via MCP. It’s how Claude Desktop is envisioned to access domain expertise.  

**2. Research-Data Access (Search Interface):** In this mode, the agent uses Deepr as a **retrieval system**. For example, an OpenAI deep-research model can call Deepr’s MCP endpoints to *search* the existing vector store or document corpus and *fetch* relevant documents. The MCP protocol here is like a custom search API: the agent issues a `search` request with a query and gets back a list of document IDs/snippets, then calls `fetch` on specific IDs to retrieve full text. This supports “Browser-access” for LLMs, enabling them to pull private knowledge.  (OpenAI’s documentation for deep research models specifically requires MCP servers to implement a search+fetch interface for private data ([www.axios.com](https://www.axios.com/newsletters/axios-ai-plus-768dbc90-1af7-11f0-826a-25dbb568702a#:~:text=intelligence%20,It%20empowers%20users%2C%20even)) ([www.itpro.com](https://www.itpro.com/technology/artificial-intelligence/what-is-model-context-protocol-mcp#:~:text=Model%20Context%20Protocol%20,the%20LLM%20via%20the%20client)).) 

**Priority:** Both use cases are strategically important. The expert-chat interface is already partially implemented and drives immediate value (letting developers ask experts for insights). The search/fetch interface unlocks powerful capabilities by integrating Deepr’s knowledge into cutting-edge agentic pipelines (like GPT-5 deep-research or multi-agent chains). **We recommend implementing both.** In practice, first stabilize and secure the existing chat MCP server, then layer on search+fetch endpoints and HTTP APIs as shown below.  OpenAI, Google, Microsoft and others expect MCP servers to allow LLMs to access tools and data; this underpins Deepr's vision of “AI that grows” ([www.axios.com](https://www.axios.com/newsletters/axios-ai-plus-768dbc90-1af7-11f0-826a-25dbb568702a#:~:text=intelligence%20,It%20empowers%20users%2C%20even)) ([www.itpro.com](https://www.itpro.com/technology/artificial-intelligence/what-is-model-context-protocol-mcp#:~:text=Model%20Context%20Protocol%20,the%20LLM%20via%20the%20client)).

# Current MCP Server Review

Deepr currently uses a **Python stdio-based MCP server** (`deepr/mcp/server.py`) and a CLI `deepr mcp serve` to launch it. The server supports JSON-over-stdin for three methods: `list_experts`, `get_expert_info`, and `query_expert`.  Key points:

- **Strengths:** 
  - **Simplicity:** No external dependencies or web server setup. Easy to launch from CLI. 
  - **Quick integration:** Designed to work with Claude Desktop by spawning a `python -m deepr.mcp.server` process (as documented in the CLI help) so that Claude’s local MCP client can pipe JSON to it. ([www.itpro.com](https://www.itpro.com/technology/artificial-intelligence/what-is-model-context-protocol-mcp#:~:text=Model%20Context%20Protocol%20,the%20LLM%20via%20the%20client)). 
  - **Basic functionality:** It correctly loads expert profiles (name, domain, stats) and runs one-off chat sessions with GPT-5 models via the `ExpertChatSession` class, returning answers with citations.  

- **Limitations:** 
  - **No standard API:** It relies on blocking stdin/stdout as the transport. This means it cannot easily be called over HTTP or by code that expects a web endpoint. Many MCP clients (e.g. OpenAI deep-research) expect a web URL.
  - **No Streaming:** All responses are returned at once upon completion. It cannot stream partial results (like GPT chat streaming) back to the caller. This limits responsiveness for long answers.
  - **No Conversation State:** Each `query_expert` call creates a new `ExpertChatSession` keyed by `expertName_id(question)`, but once done the session is discarded. There is *no multi-turn conversation or session continuity* exposed via MCP. (This contrasts with some MCP use cases where an agent might want an ongoing dialogue with one expert.)
  - **No Search/Fetch:** It only covers the “expert chat” use case. It does not support a `search` method to return document pointers, nor a `fetch` method to retrieve stored research content. Thus OpenAI’s deep-research mode cannot browse Deepr’s documents directly.
  - **Authentication & Security:** Currently there is no access control. Any process with access to run the MCP server (or call its stdin) can get data. There’s no encryption or token validation on stdin/stdout streams. As noted by reporting, MCP’s lack of built-in auth is a risk ([www.itpro.com](https://www.itpro.com/technology/artificial-intelligence/what-is-model-context-protocol-mcp#:~:text=However%2C%20MCP%20carries%20security%20risks%2C,AI%20ecosystem%20due%20to%20its)).
  - **Concurrency:** The stdio model is inherently single-process and single-threaded. It could only serve one request at a time per process. For multiple simultaneous agent connections, you’d need to spawn multiple MCP server processes manually.

*In summary*, the current MCP server is a proof-of-concept that works for basic Claude Desktop use but is **not robust or extensible** for production-grade or enterprise workflows. In particular, migrating to an HTTP/WebSocket server with JSON-RPC or REST endpoints will greatly enhance flexibility (support streaming, concurrency, auth, etc.).  

# High-Level Recommendations (Prioritized)

1. **Implement Search+Fetch Endpoints (Critical):**  
   **Impact:** Enables OpenAI and other deep-research models to query Deepr’s knowledge base; opens up RAG and multi-agent capabilities.  
   **Effort:** Moderate. Requires exposing the vector store or workspace data via MCP.  
   **Actions:** Develop an MCP *search* API that accepts a text query and returns `[ {id, title, snippet, score}, ... ]`. Implement a *fetch* API that, given an ID, returns the full document content (markdown from previous research ouputs). These can be built on Deepr’s existing vector search or file store. For example, call into the vector store with `client.files.search` or similar to retrieve the top-k matches by embedding similarity, then return their IDs and snippets. For fetch, return the stored markdown for that ID. Ensure the JSON schema matches what LLMs expect (see OpenAI’s [deep research guidelines](https://platform.openai.com/docs/guides/gpt/deep-research/mcp) which require `search` and `fetch` tools on the MCP server input). The tool calls should have `"require_approval": "never"` since they are read-only.  
   **Reference example:** An MCP config for deep research might use: 
   ```python
   client.responses.create(
       model="o3-deep-research",
       tools=[{"type": "search"},{"type": "mcp", "server_label":"deepr", "server_url":"https://host/mcp","require_approval":"never"}],
       input="Analyze our sales docs on AI strategy..."
   )
   ```
   The Deepr server must implement `/search` and `/fetch` to satisfy that call.  

2. **Adopt an HTTP/Websocket Server (High):**  
   **Impact:** Allows rich interactions (multi-turn conversations, streaming, concurrency, integration with webhooks/Rest).  
   **Effort:** Moderate to High. Need to select a web framework (e.g. FastAPI, Flask, Starlette).  
   **Actions:** Replace the stdin/stdout loop with a RESTful or WebSocket API. For example, use **FastAPI** to create endpoints:  
   - `GET /experts` (list_experts),  
   - `GET /experts/{name}` (get_expert_info),  
   - `POST /experts/{name}/chat` or `/query` (query_expert).  
   - `POST /search` (MCP search), and `GET /fetch/{doc_id}` (MCP fetch).  
   
   This allows standard clients to connect and stream. For streaming responses, you can use Server-Sent Events or WebSockets. For example, have `/experts/{name}/chat` accept a conversation ID (or assign one) and stream partial answers using [`yield` from a FastAPI route](https://fastapi.tiangolo.com/advanced/custom-response/#streaming-response). Libraries like [Starlette](https://www.starlette.io/responses/#streaming) support streaming.  

   **Code Example (Outline):** 
   ```python
   from fastapi import FastAPI, Query
   app = FastAPI()

   @app.post("/experts/{name}/chat")
   async def chat(name: str, question: str, session_id: str = None):
       # Create or reuse ExpertsChatSession
       ...
       for chunk in session.stream_query(question):
           yield chunk  # streamed back to client
   ```
   (Implementing `stream_query` by sending tokens back as they arrive from GPT.)

   **Rationale:** Streaming and conversational state drastically improves user experience. Agents can parse `"\n"` partial answers rather than waiting minutes for full output. Many MCP clients (including Claude and Cursor) expect a network API, not raw stdio. 

3. **Session & Multi-Agent Management (High):**  
   **Impact:** Supports multi-step analytic workflows and concurrent agents.  
   **Effort:** Medium. Requires tracking conversation IDs and context.  
   **Actions:** Instead of keying by question ID, maintain a session registry (in-memory or simple DB) mapping `session_id -> ExpertChatSession`. Allow clients to send a `session_id` with messages to continue the same chat (and to retrieve past context). This lets multi-turn chat with an expert. For multi-agent scenarios, you might also implement "run/chain" commands where one agent’s result can feed another’s query.  Use unique session tokens and support `GET /sessions/{session_id}/state` or similar for introspection.  

4. **Security & Authentication (High):**  
   **Impact:** Prevents data leaks and misuse; essential for enterprise use.  
   **Effort:** Medium. Needs design of auth scheme and possibly ACLs.  
   **Actions:** 
   - **Authentication:** Require API tokens or OAuth. For example, validate a custom header like `Authorization: Bearer <token>`. Use short-lived tokens or HMAC-signed session cookies. Avoid static keys. One approach is to have an *API gateway* or proxy handle auth; or implement JWT signing with public keys.  
   - **Access Control:** Limit which experts or data each user/agent can query. For instance, only a subset of experts or documents might be public. Implement checks in server logic.  
   - **Input Sanitization:** Validate all inputs. MCP requests that allow `search` should escape or limit queries.  
   - **Privacy:** Recognize that exposing a vector store potentially leaks internal info. Provide whitelist/blacklist. (TechRadar warns MCP has no built-in enterprise auth, so central identity management is needed ([www.itpro.com](https://www.itpro.com/technology/artificial-intelligence/what-is-model-context-protocol-mcp#:~:text=However%2C%20MCP%20carries%20security%20risks%2C,AI%20ecosystem%20due%20to%20its)) ([www.techradar.com](https://www.techradar.com/pro/mcps-biggest-security-loophole-is-identity-fragmentation#:~:text=To%20secure%20MCP%20and%20similar,by%20human%20or%20system%20errors)).)  
   - **Auditing:** Log all queries and fetches for post-incident review. Potentially include an optional human-in-the-loop approval for especially sensitive fetches (though deep-research requires `require_approval: never` so this may be for other usage).

5. **Integration with Existing Deepr Data (High):**  
   **Impact:** Ensures MCP calls return rich, relevant content.  
   **Effort:** Low to Medium. Build connectors.  
   **Actions:** 
   - Use the existing **vector store** (maybe OpenAI embeddings, Pinecone, etc.) for the search endpoint. E.g.: convert `vector_store.search(query)` results into MCP `search`. 
   - For document fetch, you likely have the markdown reports saved on disk. Create an ID mapping (UUID or path). The MCP search results should include this ID. 
   - If using multiple sources (web, uploaded files), unify them under the search interface.  
   - Optionally incorporate Deepr’s own RAG system: e.g. allow `mcp.fetch` to return not just raw markdown but also metadata like citations or quality scores.  
   - Example: Use `client.files.create` and `client.files.delete` in an MCP handler to respond with the content, similar to how the ExpertChatSession builds answers.

6. **Deep Research Integration Details:**  
   **Impact:** Allows GPT-5 deep-research to leverage Deepr’s experts.  
   **Effort:** High. Requires advanced MCP features.  
   **Actions:** 
   - Support the full [Deep Research API workflow](https://platform.openai.com/docs/guides/gpt/deep-research) by implementing both a `search` tool (based on internal databases or web search) and enabling **remote MCP** usage. Provide a self-descriptive `server_info` endpoint if needed.  
   - For GPT-5 deep research specifically, note that it can call your MCP server as a tool. Example from docs:
     ```python
     from openai import OpenAI
     client = OpenAI()
     resp = client.responses.create(
         model="o3-deep-research",
         background=True,
         tools=[{"type":"mcp", "server_label":"deepr", "server_url":"https://yourserver/mcp", "require_approval":"never"}],
         input="Analyze our archival sales reports..."
     )
     ```
     Ensure your server URL supports both GET and POST for the required TCP protocols.  
   - **Context Injection:** Deep-research models will likely pass the user’s question via search queries to your MCP. Be sure to include relevant context from Deepr’s knowledge base in search results.  
   - **Code Interpreter:** The deep-research model may also use `code_interpreter` for computation. Your server doesn’t need to do that, but ensure your MCP endpoints can handle calls in parallel with code tool calls.  

7. **Integration Patterns for Claude/VSCode/Cursor (Medium):**  
   **Impact:** Smooth user experience for target platforms.  
   **Effort:** Low to Medium. Mostly documentation and config.  
   **Actions:** 
   - **Claude Desktop:** Provide example `claude_desktop_config.json` entries (as in the CLI help). For example:
     ```json
     {
       "mcpServers": {
         "deepr-experts": {
           "command": "python",
           "args": ["-m", "deepr.mcp.server"],
           "env": {"OPENAI_API_KEY": "sk-..."}
         }
       }
     }
     ```
     This tells Claude to spawn the local MCP server on startup. (No citation needed here.) 
   - **Cursor IDE / Other IDEs:** Many modern coding IDEs that embed LLMs (e.g. VS Code, Jetbrains) support external tool plugins or MCP. If Cursor or similar tools support MCP, you would specify either a command (like above) or an HTTP endpoint. For example, if Cursor has a settings file, add a section:
     ```
     mcpServers:
       deepr:
         url: http://localhost:8000/mcp
         capabilities: [list_experts, query_expert, search, fetch]
     ```
     Check the tool’s docs. If only CLI is possible, using `deepr mcp serve` as a subprocess works, or consider offering a dedicated plugin.  
   - **Agent Chaining:** Train UI examples so that users can ask Claude to call “my Deepr Azure Architect expert” using natural language, as shown in Deepr’s docs. Liaise with platforms to ensure “expert names” map correctly to MCP calls.

8. **Observability and Logging (Medium):**  
   **Impact:** Improves debuggability and governance.  
   **Effort:** Low to Medium.  
   **Actions:** Instrument the MCP server to log incoming requests, response times, and errors. Integrate with Deepr’s budget tracking (e.g. log token usage per MCP call). Provide diagnostic commands (e.g. `deepr mcp stats`) so admins can see how many queries each expert handled. This aligns with Deepr’s goal of “Transparent, governed output”.

9. **Rate Limiting and Quotas (Medium):**  
   **Impact:** Protects against runaway costs or abuse.  
   **Effort:** Low to Medium.  
   **Actions:** Implement request throttling or per-user rate limits. For example, reject or delay if more than X queries per minute. Optionally tie in with Deepr’s budget system to halt the MCP server if costs exceed a threshold.  

10. **Helper SDKs/Code Examples (Low):**  
    **Impact:** Eases developer adoption and reduces errors.  
    **Effort:** Low.  
    **Actions:** Provide a small Python or JavaScript library to call Deepr’s MCP API. Document sample usage (e.g. how to list experts, create a session, handle streaming). This complements the CLI.  

# Implementation Guide & Code Examples

Below are concrete steps and code sketches to implement the above recommendations.

### 1. Build a RESTful MCP Server with FastAPI

Replace the stdio loop with a FastAPI app. For example:

```python
# mcp_server.py
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel
import asyncio

app = FastAPI()

# Pydantic models for request/response (optional)
class QueryRequest(BaseModel):
    assistant_id: str
    text: str

@app.get("/experts")
async def list_experts():
    experts = ExpertStore().list_all()
    return [{"name": e["name"], "domain": e["domain"], "description": e["description"]} for e in experts]

@app.get("/experts/{expert_name}")
async def get_expert(expert_name: str):
    expert = ExpertStore().load(expert_name)
    if not expert:
        raise HTTPException(status_code=404, detail="Expert not found")
    return {
        "name": expert.name,
        "domain": expert.domain,
        "description": expert.description,
        "documents": expert.total_documents,
        "conversations": expert.stats.get("conversations", 0),
        "total_cost": expert.stats.get("total_cost", 0.0)
    }

@app.post("/experts/{expert_name}/chat")
async def chat(expert_name: str, req: QueryRequest):
    expert = ExpertStore().load(expert_name)
    if not expert:
        raise HTTPException(status_code=404, detail="Expert not found")
    # Reuse or create session
    session = ExpertChatSession(expert, agentic=True)
    # StreamingResponse requires a generator of bytes
    async def answer_gen():
        for chunk in session.stream_query(req.text):
            yield chunk.encode('utf-8')
    return StreamingResponse(answer_gen(), media_type="text/plain")
```

*Notes:* 
- Here, `stream_query` would be a new method in `ExpertChatSession` that yields partial answer text as it is generated. Internally it would call the GPT-5 API with streaming enabled.
- Using `StreamingResponse` in FastAPI automatically streams `text/plain` to the client, so a calling LLM client sees tokens as they arrive.

### 2. Implement the MCP Search API

Define endpoints for `search` and `fetch`:

```python
@app.post("/search")
async def mcp_search(query: dict):
    """
    Expects JSON: {"query": "your text", "k": 5}
    Returns: {"results": [{"id": id, "title": title, "snippet": snippet}, ...]}
    """
    q = query.get("query", "")
    k = query.get("k", 5)
    # Perform vector search on the knowledge base
    results = vector_search(query=q, top_k=k)  # implement with your bookstore
    output = []
    for res in results:
        output.append({
            "id": res.id,
            "title": res.title,
            "text": res.snippet,  # a short excerpt
            "source": res.source_url  # optional
        })
    return {"results": output}

@app.get("/fetch/{doc_id}")
async def mcp_fetch(doc_id: str):
    """
    Returns full text for a document ID.
    """
    try:
        content = load_document_by_id(doc_id)  # read the markdown file or DB
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"id": doc_id, "text": content}
```

*Code Example:* To add documents to your vector store, after each research run you might do:
```python
# After saving markdown result to disk:
vector_store.add_file(f"docs/{filename}.md", id=document_id, metadata={"title": "Deep Dive on X"})
```

Then `vector_search` would query that store (e.g. using OpenAI embeddings or an API like Pinecone).  

### 3. Enable Streaming and Partial Responses

In the `ExpertChatSession`, split the response generation into chunks. For example:

```python
class ExpertChatSession:
    def stream_query(self, question: str):
        # Example using OpenAI Python SDK with streaming
        response = openai.ChatCompletion.create(
            model="gpt-5",
            messages=[{"role": "user", "content": question}],
            stream=True
        )
        for chunk in response:
            if 'choices' in chunk:
                text = chunk['choices'][0]['delta'].get('content', '')
                yield text  # this is sent chunk by chunk
```

This way, your FastAPI route returns each token in real time. The MCP client (like Claude Desktop) can render partial answers immediately.

### 4. Support Multi-Turn Sessions

Modify your chat endpoint to accept an optional `session_id`:

```python
@app.post("/sessions/{session_id}/chat")
async def chat_session(session_id: str, req: QueryRequest):
    session = session_registry.get(session_id)
    if not session:
        session = ExpertChatSession(expert, agentic=True)
        session_registry[session_id] = session
    def answer_gen():
        yield from session.stream_query(req.text)
    return StreamingResponse(answer_gen(), media_type="text/plain")
```

Clients can generate or supply a unique `session_id`. You might return a `Set-Cookie: sessionId=...` header or JSON field with the new ID on first call. This enables keeping context (previous turns) alive in `session`.

### 5. Add Authentication

Wrap the FastAPI app with middleware or decorators to check a token. For simplicity:

```python
from fastapi import Security
from fastapi.security.api_key import APIKeyHeader

api_key_header = APIKeyHeader(name="Authorization")

def verify_token(api_key: str = Security(api_key_header)):
    if api_key != f"Bearer {YOUR_SECRET_KEY}":
        raise HTTPException(status_code=401, detail="Unauthorized")

@app.get("/experts", dependencies=[Security(verify_token)])
async def list_experts():
    ...
```

Alternatively, integrate OAuth2 or JWT. At minimum, require a bearer token or Basic Auth so that random processes can’t access your data.  

### 6. Test with OpenAI Deep Research

Once `/search` and `/fetch` are live, configure a deep research call. Example (using pseudo-code):

```python
import requests
from openai import OpenAI

client = OpenAI()

# Register your MCP server in OpenAI (if needed) & then:
response = client.responses.create(
    model="o3-deep-research",
    background=True,
    tools=[{"type": "mcp", "server_label": "deepr_ser", "server_url": "https://mydeepr.com/mcp", "require_approval": "never"}],
    input="Summarize our company's product documentation and strategic outlook."
)
```

OpenAI should issue MCP `search` calls to `https://mydeepr.com/mcp/search` and `fetch` calls to `/fetch`. Monitor your server logs to ensure correct operation. Since deep-research models do not prompt for clarification (unlike ChatGPT’s UI version), your `search` endpoint should handle direct queries robustly.

### 7. Security Best Practices (Identity, Limiting Abuse)

- **Ephemeral Credentials:** As tech commentary warns, avoid static keys ([www.techradar.com](https://www.techradar.com/pro/mcps-biggest-security-loophole-is-identity-fragmentation#:~:text=To%20secure%20MCP%20and%20similar,by%20human%20or%20system%20errors)). Consider rotating tokens or issuing one-use temporary keys for long-running agent sessions.  
- **Segmentation:** If exposing multiple experts, consider “expert-specific” tokens so that a compromise of one token doesn’t leak all domains.  
- **Prompt Injection Defense:** Validate that `query` strings in `/search` are indeed queries, not malicious payloads. If they include markdown or special commands, sanitize or escape them. Even though your server is just fetching text, any dynamic code execution (like allowing Python in code blocks) should be guarded against.  
- **Logging & Monitoring:** Log all incoming requests (paths and parameters). Use HTTPS (via a reverse proxy like Nginx) to encrypt data in transit. This aligns with enterprise best practices cited in the IBM-Anthropic security guide ([www.techradar.com](https://www.techradar.com/pro/anthropic-and-ibm-want-to-push-more-ai-into-enterprise-software-with-claude-coming-to-an-ide-near-you#:~:text=The%20move%20reinforces%20IBM%27s%20focus,9)).  

### 8. Example: MCP Protocol (Pseudo-Client View)

To illustrate how an AI agent would use the MCP server, consider this dialogue:

- Agent: *"List my Deepr experts."*  
  The agent’s MCP client sends `{ "method": "list_experts" }` to `http://server/list_experts`.  
  **Server** responds with JSON list of experts.

- Agent: *"I’m asking the Azure Architect expert: how do I set up landing zones?"*  
  The agent decides to use `query_expert`:
  ```
  Request: POST /experts/AzureArchitect/chat
  Body: { "assistant_id":"abc123", "text":"How do I set up landing zones?" }
  ```
  **Server** streams chunks of the expert’s answer.

- Agent (Deep Research): *"Find documents about Azure landing zones."*  
  The agent sends:
  ```
  Request: POST /search
  Body: { "query":"Azure landing zones tutorial", "k": 3 }
  ```
  **Server** returns IDs of up to 3 relevant docs with excerpts. The agent then may send:
  ```
  Request: GET /fetch/{doc_id}
  ```
  for one or more IDs to read the full content.

These patterns show how Deepr’s server can serve as both an **answer engine** and a **knowledge base**.

# Next Steps

- **Prototype Search/Fetch:** Immediately implement minimal `search` and `fetch` handlers using the existing vector store and file outputs. Test with a few queries to confirm correct operation.
- **Switch to HTTP API:** Refactor the MCP server to use FastAPI or similar. Start by copying the above examples. Ensure all existing functionality (list/get/query) still works via GET/POST.
- **Session & Streaming:** Update `ExpertChatSession` to yield tokens and manage sessions. Test with manual clients (curl, websocat) to ensure the streaming responses flow.
- **Secure the Server:** Before exposing publicly or linking to any external connector (like Claude), add a simple API key check. Use HTTPS.
- **Integration Tests:** Use OpenAI’s library to simulate a deep-research call against your server, verifying the protocol adherence (mock if necessary). Also test Claude Desktop using the `deepr mcp serve` command.
- **Documentation:** Update the Deepr README/config docs with examples for various integrations (add a snippet for Cursor if possible by analogy). Provide sample code (as above) in the repo.
- **Monitoring:** Add logging and basic metrics (e.g. count of calls to each endpoint). This helps refine rate-limiting or diagnose issues.
- **Iterate:** Based on real usage, refine which expert calls are most common, whether more detailed filtering is needed, etc. If agents frequently do multi-turn tool-chains, improve context handling (vector store context injection, knowledge graph linking).
- **Stay Aligned with Roadmap:** On Deepr’s roadmap, MCP integration is Phase 2. After server basics (list, query) and advanced features (search/fetch), move to tasks like provider routing optimization and additional semantic commands. Use the MCP server to funnel diagnostics or memory hooks (e.g. discovery of stale knowledge as described in Phase 1 tasks).

By following these recommendations, Deepr will have a robust MCP implementation that not only serves **human-driven runs** but also empowers **AI-driven research workflows**, consistent with its vision of an intelligent, continuously learning knowledge infrastructure.  

