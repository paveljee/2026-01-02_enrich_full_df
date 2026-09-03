# Test fixtures
## `operator_accepted_aziz_sheikh_push.json`
This is the exact `POST /push` request body
produced by Codex and accepted by the Backend
during the 2026-09-03 Human Operator end-to-end run
(`pixi run test-detour-ai-augment-operator`)
for `'{"ktp.first_name":"A.","ktp.last_name":"Sheikh"}'`.

It anchors the regression covering Backend validation,
synthetic commit linkage, projection, and
the terminal `GET /pull -> 410 Gone` response.

The content of this was copied and pasted by
the Human Operator manually from shell output.

The captured terminal response is not tracked
because its optional second line contained production ground truth.
The regression derives its accepted-values line exactly from this fixture
and supplies synthetic ground truth instead.
