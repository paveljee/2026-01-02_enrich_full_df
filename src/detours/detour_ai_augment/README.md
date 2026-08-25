# KTP HCR Detour: AI Augmentation

> [!IMPORTANT]
> This document contains minimal AI-generated text and was primarily written by [@paveljee][paveljee]

A reproducible architecture for running an isolated AI agent against a task-oriented backend API.
The AI Agent Runtime pulls work from the Backend, uses an LLM Inference API to complete it, and pushes the result back. A Human Operator deploys, operates, and reviews the system through a Control Centre.
This is a **feature** in the KTP HCR project.

## Architecture

The architecture is described in [Acme][acme-1997]-ish terms,
the "ish" being due to the fact that
the description does not necessarily subscribe to Acme in full complete faith
but rather reuses some of the basic primitives from the 1997 paper.
A specific formal implementation,
perhaps at an even higher level of abstraction than Acme, is
the [RDF/Turtle file](./assets/hcr_augment_agent_architecture.drawrdf.ttl)
from which the below diagram was [programmatically derived][giacomociti-rdf2dot].

![HCR Augment Agent Architecture](./assets/hcr_augment_agent_architecture.svg)

_Figure 1. Architecture of the AI Augmentation Detour of the KTP HCR Pipeline. `owl:NamedIndividual` indicates that each graph node is declared as an individually identifiable entity in the ontology._

**Abbreviations:** AI, artificial intelligence; API, application programming interface; DB, database; HCR, [Highly-Cited Researcher][clarivate-hcr]; KTP, [Knowledge Translation Program][ktp]; LLM, [large language model][google-kg-llm]; OWL, [Web Ontology Language][owl2]; RDF, [Resource Description Framework][rdf11].

----

The architecture contains five **components** (Figure 1).

* **Human Operator** — operates
  the Control Centre, AI Agent Runtime, and Backend.
  The operator may also operate the Inference API when it is self-hosted.
* **Control Centre** — orchestrates
  the AI Agent Runtime and Backend.
* **AI Agent Runtime** — runs
  the agent and acts as an API client of the Backend.
* **LLM Inference API** — provides
  large language model (LLM) inference to the AI Agent Runtime.
  OpenAI is the default provider (some alternatives: OpenRouter, Ollama).
* **Backend** — exposes
  the task API and stores application data, logs, and submissions.

The AI Agent Runtime and Backend must be deployed as separate systems.
The Backend may run on the Control Centre host or on another server,
but it must not run inside the AI Agent Runtime.
The AI Agent Runtime must not run on the Control Centre host
except as a guest virtual machine (VM, e.g., Lima on macOS).

The LLM Inference API accesses the Backend API by operating the AI Agent Runtime;
more precisely, the API calls are invoked by the Runtime itself
whereas generative outputs of _some_ of these calls trigger tools on the Runtime
as in routine [LLM function calling][openai-function-calling].

The LLM Inference API and the AI Agent Runtime are
not authorized to access the Backend proper
except via the exposed Backend API.

Neither the LLM Inference API
nor the AI Agent Runtime is
authorized to access the Control Centre.

The specific **component ports** as well as
the **connectors** and **connector roles**
to complete the Acme-ish description of 
the **system** architecture of the feature
may be prescribed elsewhere, e.g., in
`tasks/tasks-20260731-tighten-api/src/TASK.md`,
where the description of **connector properties** is
given as [Gherkin][gherkin-docs]-ish **scenarios**.

## Workflow

1. The Human Operator deploys\* the Backend API.
1. The Human Operator provisions\* or starts the AI Agent Runtime.
1. The Human Operator connects\* to the AI Agent Runtime over the SSH (Secure Shell) protocol and initiates\* a request to the LLM Inference API (e.g., by sending a prompt into the chat interface of the [OpenAI Codex Visual Studio Code extension][codex-vsce]).
1. The AI Agent Runtime, operated by the LLM Inference API, retrieves a task (e.g., a highly-cited researcher profile to augment) from the Backend API `/pull` endpoint.
1. The AI Agent Runtime works on the task by dispatching sequential\*\* requests to the LLM Inference API while the Inference API triggers tools (e.g., Linux shell commands) on the Runtime at its discretion.
1. At some point during the rollout, the AI Agent Runtime is expected to push the result to the Backend API.
1. Upon receipt of a `/push` payload, the Backend API records receipt, validates the payload, and communicates an automated response to the AI Agent Runtime.
1. The rollout continues until the AI Agent Runtime hits a `task_complete` event, as triggered by the LLM Inference API.
1. Once the Agent Runtime has marked the task as completed, it stops operation and remains idle until rehydrated by the Human Operator.
1. The Human Operator reviews Backend logs and submissions and repeats or adjusts the workflow as necessary.
1. Multiple tasks (e.g., HCR profiles) may be passed by the Human Operator to the AI Agent Runtime in a single batch; in this instance the rollout is expected to continue and only trigger a `task_complete` even once the batch is exhausted, though this is ultimately at the discretion of the LLM Inference API.

\* Either manually or via orchestration through the Control Centre.

\*\* Note that the [Multi-agent mode][openai-multi-agent] is disabled in this AI Agent Runtime.

## Directory contents and lockfile

This section is intended to capture the specifics of the workflow operation in sufficient detail to be reproduced.

> [!NOTE]
> Note that the behaviour of the LLM Inference API, unless self-hosted and specially provisioned (not by default), is fundamentally irreproducible. As such, it is only recorded as observed as an audit trail (e.g., as a OpenAI Codex JSON Lines rollout).
>
> The decision not to self-host an LLM Inference API was driven by the fact that the augmentation pipeline depends heavily on web search and web page retrieval, which are inherently irreproducible as usually implemented. For example, the open source [Tongyi Deep Research][tongyi] pipeline, while supporting open-weight models, still relies on third-party services such as Serper for web search or Jina for web page retrieval, substantially relaxing end-to-end reproducibility guarantees in general. Additionally, frontier agentic set-ups such as OpenAI Codex often offer [superior][artificial-analysis-coding-agents] performance on tasks such as software engineering, as well as across the board.

**Control Centre:** Requires no specialized infrastructure beyond a computer capable of operating the workflow components, including sufficient computing resources and internet access. The test set-up (hereafter: the main host) used a Mac16,12 Macbook Air (Apple M4 chip) in a 10-core, 24 GB RAM, 512 GB SSD configuration, running macOS Sequoia 15.6.1 and Visual Studio Code 1.130.0, though these versions were not pinned and may have been updated moving forward.

**Backend:** Deployed on the host machine using `./src/backend/api.py` in this (i.e., the `detour_ai_augment` “detour” of the KTP HCR pipeline) environment.
`pixi.lock` and `pyproject.toml` in the repository root provide the pinned Python config.
The version of pixi is locked in `.tool-versions`.

**AI Agent Runtime:** Deployed under the main host to a [Lima virtual machine version 2.2.0][lima220] using `./src/agent_runtime/deploy.sh`.

More needs to be said about the Control Centre – AI Agent Runtime dynamics, so there is a separate section dedicated to this down below.

## Control Centre vs. AI Agent Runtime – Harnessing software that also has agency
As described above, the AI Agent Runtime is co-operated by the Human Operator and the LLM Inference API.
While the Human assumes a more supervisory role, principal operations are undeniably handed over to the LLM Inference API.
This status quo is peculiar because this AI Agent Runtime both orchestrates and authorizes tool calls such as Linux shell commands.
Note that this Runtime authorizes OpenAI Codex to run in the `danger-full-access` sandbox mode, which means unrestricted access to the (virtual) machine on which and under which user the executable is running.
This authorization is helpful to ensure stable autonomous work of the Runtime, which is contingent on its ability to execute any commands as generated by the LLM Inference API.

This peculiarity is immediately visible if we consider how Unix Discretionary Access Control (DAC) privileges work for the Runtime.
Tool calls are invoked by an executable that interacts with the LLM Inference API, e.g., an OpenAI Codex binary.
The executable, in turn, runs under permissions that were bestowed upon it by the Human Operator.
These permissions are inherited by the tool calls that the executable initiates.
For example, it turns out to be difficult to have the executable both write the session log into a file while at the same time restricting the executable from tampering with the file using LLM-generated shell commands.

This effect on the session log is particularly unfortunate because it forces the Human Operator to regard it as an untrusted artifact _despite_ its being generated by a deterministic process, _specifically_ due to the fact that the Runtime may in principle tamper with the artifact in retrospect by leveraging its tool calling capabilities.

This vulnerability was countered by the Control Centre implementing a series of measures:

- The deployment script `./src/agent_runtime/deploy.sh` provisions a non-root user account under which VS Code Server and Codex extension are installed and executed. This effectively limits the scope of system permissions, such as passwordless sudo.
- Before launching Codex, under a root user (inside the virtual machine), a watcher `./src/agent_runtime/appendwatch/appendwatch.py` is running that monitors events within the `$CODEX_HOME/sessions` directory, where the Codex app stores session logs.
The watcher tracks changes applied to session files using `inotify` and permanently flags any rollouts on which non-append-only changes were observed.
- Both the watcher and the report it maintains are persisted beyond Codex’s user account (i.e., under root-only permissions), placing them out of reach of the AI Agent Runtime.

Programmatic measures on the Control Centre’s end are supplemented with measures for which the Human Operator is responsible:

- The report directly informs review of AI Agent Runtime submissions on the Backend: rollouts marked as compromised are tracked down to the corresponding submissions and invalidate them.
- **As an important closing step, the human operator must review the session chat (i.e., as rendered by the VS Code extension), including any collapsed sections, before closing the Codex session to spot any obviously suspicious tool calls.** This step might be the most difficult to tamper with, as, upon adversarial testing, even if the underlying rollout is compromised, the already-rendered chat is not replaced _unless_ VS Code/the extension is restarted.

The probability of rollout compromise is estimated to be quite small, but it is [non-zero][gh-issue-rollout-self-ingest].
In contrast, the defensive measures in place tentatively establish session rollouts as _trusted_ artifacts, enabling their downstream use, for example, as a faithful record of web search tool outputs.

## Note on self-hosting LLM Inference API
This specific set-up has been tested, to a degree, for the feasibility of reproducing it with a self-hosted LLM Inference API instead of OpenAI.

**Takeaway: The KTP HCR AI Augmentation detour architecture ([Figure 1](#architecture)) can be successfully deployed and run as documented using a self-hosted LLM Inference API instead of OpenAI.**
Caveat: Provisioning a separate web search / web page retrieval service (e.g., Serper or Jina, respectively) would be necessary, and some of the intended Codex tooling would not work (or would not work as expected).
This caveat was an important reason behind the decision to go with OpenAI on this project despite the vendor lock and token-for-token irreproducibility in the long run as older models get deprecated by the provider – coupled with the expected overall better performance of a frontier LLM such as GPT-5.6-Sol over a smaller self-hosted model, and considering the generous Codex usage allowance coming with ChatGPT Plus pricing (e.g., CA$28.24/month inclusive of applicable taxes as of August 2026).

To smoke-test the feasibility of this, on August 6^th^, 2026, UTC-4, a Human Operator completed the following steps:

* Deployed a virtual machine using `src/detours/detour_ai_augment/src/agent_runtime/deploy.sh` under [Lima 2.2.0][lima220] under an arm64 macOS host as [specified above](#directory-contents-and-lockfile).
* SSH’d into it  as `$AIVM_USER` and opened a session with GNU bash version 5.2.21(1).
* Installed a standalone instance of codex-cli `VERSION="0.146.0-alpha.3.1"` using this command: `curl -fsSL https://chatgpt.com/codex/install.sh | sh -s -- --release "$VERSION"`
* Logged in using Human Operator’s ChatGPT Plus credentials.
* Note that the `~/.codex/config.toml` file was automatically picked up as provisioned at deploy from `src/detours/detour_ai_augment/src/agent_runtime/provision.sh`.
* Replaced the `model` definition in `config.toml` with the following:

    ```toml
    model = "default"
    model_provider = "llamacpp"

    [model_providers.llamacpp]
    name = "llama.cpp"
    base_url = "http://192.168.5.2:8000/v1"
    wire_api = "responses"
    requires_openai_auth = false
    ```
* On the macOS host, downloaded one of the latest llama.cpp releases, which was [b10295][llamacpp-b10295] at the time, for macOS ARM64 (`llama-b10295-bin-macos-arm64.tar.gz`), optimized for the [Metal backend][llamacpp-kleidiai-disabled-pr].

    > [!NOTE]
    > Some of the earlier releases did not support all Codex features used in this set-up, for example, `"name":"run","namespace":"web"` for `function_call`’s, which is relied on _heavily_ when validating submissions in `src/detours/detour_ai_augment/src/backend/api.py`.
* Removed macOS Gatekeeper’s quarantine on the downloaded package to enable execution: `LLAMA_RELEASE="10295" && /usr/bin/xattr -d com.apple.quarantine "$HOME/Downloads/llama-b${LLAMA_RELEASE}-bin-macos-arm64.tar.gz"`
* Deployed llama.cpp on the macOS host. A sample deployment, particularly llama.cpp configurations used, is documented here: `src/detours/detour_ai_augment/src/llm_inference_api/sample_deploy/`
    * Note that llama.cpp was deployed in a non-router mode, hence the `default` model name in `config.toml` above.
    * Note also that the proxy server that is used there is completely optional and provided for illustrative purposes.
* On the macOS host, launched the detour Backend API (i.e., using `pixi run serve`).
    * Note that a non-default port (e.g., `8612`) was used for the Backend API so as not to collide with the default `8000` port on which the self-hosted LLM Inference API would already be running in this set-up.
    * Note also that the `aivm-appendwatch` service, responsible for continuously verifying the integrity of Codex rollouts, would also have been provisioned already and running by that point as part of the AIVM deployment process.
    * A helpful command to monitor `appendwatch` statuses on AIVM is this (to be run under a root user): `MOUNT_DIR=/path/to/mounted/dir/on/macos && watch --interval=1 cat "$MOUNT_DIR/.aivm-control/appendwatch/appendwatch-tree.txt"`
* Codex CLI was prompted in a non-interactive mode: `codex exec --skip-git-repo-check "http://192.168.5.2:8612/openapi.json"`
    * Note that the URL here is _the_ prompt.

Two sample rollouts from these runs are provided for reference from these runs at `src/detours/detour_ai_augment/src/llm_inference_api/sample_rollouts`:

* `gemma-4-e4b-it-Q4_K_M-reasoning-off.jsonl` documents the performance of [Gemma 4 E4B][google-gemma-4-model-card] (in the `ggml-org/gemma-4-E4B-it-GGUF` variant, as of [commit 6b352c5][gemma-4-E4B-it-GGUF-6b352c5], `Q4_K_M` quantized) with reasoning turned off; 
* `gpt-oss-20b-mxfp4-reasoning-high.jsonl` documents the performance of [GPT OSS 20B][arxiv-gpt-oss-model-card] (in the `ggml-org/gpt-oss-20b-GGUF` variant, as of [commit e1dc459][gpt-oss-20b-GGUF-e1dc459], `MXFP4` quantized) with reasoning set to `high` (in the llama.cpp server config; the value from `config.toml` was ignored).

See the exact llama.cpp server configurations used for both models at `src/detours/detour_ai_augment/src/llm_inference_api/sample_deploy/`

The rollouts can be reviewed with this tool: `src/github.com/simonw/tools/blob/266b40cbefe398ec5a03b695f107cab7a5713529/codex-timeline.html`

Note that the runs were done on a “dirty” virtual machine (i.e., an AIVM instance already provisioned earlier), hence the documented GPT OSS’s behaviour when it detected unrelated files in the working directory.

<!--- Markdown references --->

[paveljee]: https://github.com/paveljee "paveljee (Pavel Zhelnov) | GitHub"

[acme-1997]: https://dl.acm.org/doi/abs/10.5555/782010.782017 "David Garlan, Robert Monroe, and David Wile. 1997. Acme: an architecture description interchange language. In Proceedings of the 1997 conference of the Centre for Advanced Studies on Collaborative research (CASCON '97). IBM Press, 7."

[ktp]: https://knowledgetranslation.net/featured-project-research-integrity-project-exploring-diversity-in-clarivates-highly-cited-researchers-list/ "Knowledge Translation Program"

[clarivate-hcr]: https://clarivate.com/highly-cited-researchers/ "Clarivate Highly Cited Researchers"

[owl2]: http://www.w3.org/TR/owl2-overview/ "OWL 2 Web Ontology Language Document Overview: W3C Recommendation"

[rdf11]: http://www.w3.org/TR/rdf11-concepts/ "RDF 1.1 Concepts and Abstract Syntax: W3C Recommendation"

[giacomociti-rdf2dot]: https://giacomociti.github.io/rdf2dot/ "giacomociti/rdf2dot | A simple RDF visualization tool based on GraphViz"

[gherkin-docs]: https://cucumber.io/docs/gherkin/reference "Gherkin Reference | Cucumber"

[google-kg-llm]: https://www.google.com/search?kgmid=/g/11kc9956b3 "Large language model - Google Knowledge Graph ID"

[openai-function-calling]: https://developers.openai.com/api/docs/guides/function-calling "Function calling | OpenAI Developers"

[codex-vsce]: https://marketplace.visualstudio.com/items?itemName=openai.chatgpt "Codex – OpenAI’s coding agent | Visual Studio Code Marketplace"

[openai-multi-agent]: https://developers.openai.com/api/docs/guides/responses-multi-agent "Multi-agent | OpenAI Developers"

[lima220]: https://github.com/lima-vm/lima/releases/tag/v2.2.0 "lima release v2.2.0 | GitHub"

[tongyi]: https://github.com/Alibaba-NLP/DeepResearch "Tongyi Deep Research | GitHub"

[artificial-analysis-coding-agents]: https://artificialanalysis.ai/agents/coding-agents "Artificial Analysis Coding Agent Benchmarks | Artificial Analysis"

[gh-issue-rollout-self-ingest]: https://github.com/openai/codex/issues/27131 "Codex self-ingests local session JSONL logs during token-usage investigation, causing runaway token growth #27131 | GitHub"

[llamacpp-b10295]: https://github.com/ggml-org/llama.cpp/releases/tag/b10295 "Release b10295 · ggml-org/llama.cpp"

[llamacpp-kleidiai-disabled-pr]: https://github.com/ggml-org/llama.cpp/pull/23780 "ci : move ARM jobs to self-hosted + disable kleidiai mac release- #23780"

[google-gemma-4-model-card]: https://ai.google.dev/gemma/docs/core/model_card_4 "Gemma 4 model card"

[gemma-4-E4B-it-GGUF-6b352c5]: https://huggingface.co/ggml-org/gemma-4-E4B-it-GGUF/tree/6b352c53e1d2e4bb974d9f8cafcf85887c224219 "ggml-org/gemma-4-E4B-it-GGUF at 6b352c53e1d2e4bb974d9f8cafcf85887c224219"

[arxiv-gpt-oss-model-card]: https://doi.org/10.48550/arXiv.2508.10925 "gpt-oss-120b & gpt-oss-20b Model Card"

[gpt-oss-20b-GGUF-e1dc459]: https://huggingface.co/ggml-org/gpt-oss-20b-GGUF/tree/e1dc459feff949ff451ce107337a2026daa80df8 "ggml-org/gpt-oss-20b-GGUF at e1dc459feff949ff451ce107337a2026daa80df8"
