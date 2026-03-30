# LangChain and LangGraph Usage in This Project

This project uses both LangChain and LangGraph together.

## 1) Where LangChain Is Used

### A. Tool definitions (`@tool`)
LangChain's tool system (`langchain_core.tools.tool`) is used to expose Python functions as callable agent tools.

Files:
- `framework/tools/email_parser.py`
- `framework/tools/log_group_discovery.py`
- `framework/tools/cloudwatch_fetcher.py`
- `framework/tools/dependency_checker.py`
- `framework/tools/service_registry.py`
- `framework/tools/teams_notifier.py`
- `framework/tools/comprehensive_validator.py`
- `framework/core/agent.py` (`store_correction` tool)

How it helps:
- Gives the model structured function-calling capability.
- Lets the agent call AWS/logging/parsing functions with typed arguments.
- Keeps tool logic separate from reasoning logic.

### B. LLM adapter (`ChatOllama`)
`langchain_ollama.ChatOllama` is used in `framework/core/agent.py` to connect the agent to the Ollama model.

How it helps:
- Standard LangChain chat model interface for local Ollama models.
- Centralized model config (`base_url`, `model`, `temperature`, timeout).

### C. Tool invocation style in tests
Tool-level tests call tools via LangChain's tool interface:
- `parse_aws_alert_email.invoke(...)`
- `fetch_service_info.invoke(...)`

File:
- `tests/run_evals.py`

How it helps:
- Tests tools exactly as the agent would call them.

## 2) Where LangGraph Is Used

LangGraph is used to build and execute the ReAct agent loop.

### A. Agent construction
In `framework/core/agent.py`:
- `from langgraph.prebuilt import create_react_agent`
- `self.agent = create_react_agent(model=self.llm, tools=self.tools, prompt=system_prompt)`

How it helps:
- Creates the reasoning + tool-calling execution graph.
- Handles iterative ReAct flow (reason -> call tool -> observe -> continue).
- Enforces recursion/iteration boundaries using runtime config.

### B. Runtime execution
Still in `framework/core/agent.py`, execution happens via:
- `self.agent.invoke(...)`

Used in:
- `process_event(...)`
- `process_text(...)`

How it helps:
- Runs the compiled graph for each event/user input.
- Returns final messages plus tool call outputs.

## 3) How Execution Flows in This Repo

1. `main.py` builds `ALL_TOOLS` (LangChain tools).
2. `main.py` creates `Agent(config, tools, memory)`.
3. `Agent.__init__` creates:
   - LangChain `ChatOllama` model
   - LangGraph ReAct agent via `create_react_agent(...)`
4. On incoming event/text:
   - `agent.process_event(...)` or `agent.process_text(...)`
   - calls `self.agent.invoke(...)` (LangGraph execution)
5. During invoke:
   - LangGraph orchestrates the loop
   - LangChain tool wrappers execute underlying Python functions
6. Final response is logged and stored in memory.

## 4) Practical Summary

- LangChain in this project provides:
  - tool abstraction (`@tool`)
  - model adapter (`ChatOllama`)
- LangGraph provides:
  - orchestration/runtime of the ReAct workflow (`create_react_agent` + `.invoke`)

So this codebase is not choosing one over the other; it uses LangChain components inside a LangGraph-driven execution flow.
