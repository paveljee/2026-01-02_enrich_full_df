Date of creation of
this README:
July 31, 2026, UTC-4

This dir
`chats-20260731-tighten-api`
contains
the complete log of
the interaction with OpenAI Codex
(i.e., a Codex rollout) in relation to the
implemention of this task specification:
`tasks/tasks-20260731-tighten-api/SPEC.md`.
This includes the rollout
`rollout-2026-07-31T14-42-27-019fb97c-1e5a-7830-9244-bd5a10a9cb73.jsonl`.

While the rollout is a
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

The directory also contains `chatgpt.md`,
which is an export of a separate ChatGPT chat
produced via ChatGPT iOS app on 2026-08-06 UTC-4
on a ChatGPT Plus subscription,
with GPT-5.6-Sol (reasoning: high),
with custom instructions
`each word of response costs $1000 so uses them wisely`
and the "memory" feature disabled.
The file `./raw_chat_api_json/chatgpt.json`
is the raw JSON files
obtained from OpenAI API
using [ChatGPT Exporter 2.32.3 by pionxzh](https://greasyfork.org/scripts/456055),
from which ultimately `chatgpt.md` was produced
using this [custom app](https://github.com/paveljee/chat-viewer).
That project uses Tampermonkey exporter outputs and scripts as reference material.
Thanks to their authors:
[Claude API Exporter 5.4.1 by MRL](https://update.greasyfork.org/scripts/542117/Claude%20API%20Exporter.user.js) and
[ChatGPT Exporter 2.32.0 by pionxzh](https://update.greasyfork.org/scripts/456055/ChatGPT%20Exporter.user.js).
