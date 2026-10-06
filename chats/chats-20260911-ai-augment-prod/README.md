Date of creation of
this README:
September 11, 2026, UTC-4

This dir
`chats-20260911-ai-augment-prod`
contains
an incomplete log of
the interaction with OpenAI Codex
(i.e., a Codex rollout) in relation to the
implemention of this task specification:
`tasks/tasks-20260911-ai-augment-prod/SPEC.md`.
This includes the rollouts:

- `rollout-2026-09-11T15-54-34-01a0912d-8624-7723-82ad-e69aadb05be7.jsonl.tgz`;
- `rollout-2026-09-14T20-37-01-01a0a1a3-3069-75f0-8dbc-63015a7ef354.jsonl.tgz`;
- rollout-2026-09-22T23-46-18-01a0cb83-59dc-78d3-aaf6-e1fbacdcf6f1.jsonl (intentionally missing);
- rollout-2026-10-06T13-52-46-01a1117c-fa4c-7b03-be06-57781ae64c5d.jsonl (intentionally missing).

The first missing rollout session was largely limited to the work
recorded in the commit `dea2bf1010d29e8b0aff14f6cb57f655b0940dae`.
It was intentionally omitted because it was too noisy to share.
For example, the usual conversation flow broke due to the human operator's
inability to elicit appropriate edits, and thus the human edited the code themself
while sending concurrent instructions to the agent to follow up/complete the edits,
which ultimately made the rollout irrepresentative of the process,
that is, to get the full picture, it would also be necessary to have a record of
concurrent human edits, which was never captured.
The second missing rollout was created to properly transition
from `gpt-6-sol` to `gpt-6.1-sol` 
(which I then rolled back again to `gpt-6-sol`
because I had concerns about performance) and
was not captured for similar reasons.

While the rollout is a
(sometimes tar/gzipped)
plain text file
(JSON Lines), 
openable with any text editor,
a special viewer tool is helpful to
open it in a more human-readable way.
The viewer is found here:
`/src/github.com/simonw/tools/blob/266b40cbefe398ec5a03b695f107cab7a5713529/codex-timeline.html`

Or online:
<https://tools.simonwillison.net/codex-timeline>

Just open the HTML page/
link using any web browser
(e.g., Chrome) and
drag and drop the rollout file
onto the viewer panel.

The directory also contains `ChatGPT-Discover_Web_Run_Schema.md`,
which is an export of a separate ChatGPT chat
produced via chatgpt.com on 2026-09-18 UTC-4
on a ChatGPT Pro subscription,
with GPT-6-Astra (reasoning: pro),
with custom instructions
`each word of response costs $1000 so uses them wisely`
and the "memory" feature disabled.
The file `./raw_chat_api_json/ChatGPT-Discover_Web_Run_Schema.json`
is the raw JSON file
obtained from OpenAI API
using [ChatGPT Exporter 2.32.3 by pionxzh](https://greasyfork.org/scripts/456055),
from which ultimately `ChatGPT-Discover_Web_Run_Schema.md` was produced
using this [custom app](https://github.com/paveljee/chat-viewer).
That project uses Tampermonkey exporter outputs and scripts as reference material.
Thanks to their authors:
[Claude API Exporter 5.4.1 by MRL](https://update.greasyfork.org/scripts/542117/Claude%20API%20Exporter.user.js) and
[ChatGPT Exporter 2.32.0 by pionxzh](https://update.greasyfork.org/scripts/456055/ChatGPT%20Exporter.user.js).
