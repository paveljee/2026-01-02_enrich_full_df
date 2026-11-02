# Test fixtures
## `operator_accepted_aziz_sheikh_push.json`
This fixture is adapted from the exact `POST /push` request body
produced by Codex and accepted by the Backend
during the 2026-09-03 Human Operator end-to-end run
(`pixi run test-detour-ai-augment-operator`)
for `'{"ktp.first_name":"A.","ktp.last_name":"Sheikh"}'`.
The adaptation specifically entailed:
for the current schema, the captured `GB` location is represented as `GBR`,
the residence source is tagged `professional_affiliation`,
the age field pairs the excerpt's reported birth year with a computed age
(the acceptance test refreshes `as_of` to the UTC push date),
and the four current academic positions specify `start: NR` and `end: NA`.
The remaining content comes from the original capture.

It anchors the regression covering Backend validation,
synthetic commit linkage, projection, and
the final `GET /pull -> 410 Gone` response.

The content of this was copied and pasted by
the Human Operator manually from shell output.

The captured final response is not tracked
because its optional second line contained production ground truth.
The regression derives its accepted-values line exactly from this fixture
and supplies synthetic ground truth instead.
