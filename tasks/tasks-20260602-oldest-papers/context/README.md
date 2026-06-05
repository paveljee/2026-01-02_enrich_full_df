This run
`tasks/tasks-20260602-oldest-papers/context/diagnostics/20260604_122608_mode1_v2_ssn_hit_v2_openalex`
contains the first complete run
after implementing OpenAlex title retrieval.

Full run is
embargoed until further notice
because it contains manual team’s notes.

SHA256 sum for
`data/openalex_paper_title_log.jsonl`
produced from the run:
`992126c8306a027fcd3d9b680811320863681be908e858f569fcc2de31782f32`.

That jsonl file is
tracked in the commit
`ae43f6aa18a1bd7b69e3ddb0c4a664864fcd1f64`.

Note that
the file was
originally dumped with
`ensure_ascii=False`, so
to fix Unicode,
I had it rewritten
using this:

```bash
% pixi run python - <<'PY'
import json, tempfile, pathlib
path = pathlib.Path("data/openalex_paper_title_log.jsonl")
with path.open("r", encoding="utf-8") as fin, tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=path.parent) as tmp:
    tmp_path = pathlib.Path(tmp.name)
    for line in fin:
        if not line.strip():
            continue
        record = json.loads(line)
        dumps = lambda o: json.dumps(o, ensure_ascii=False) + "\n"
        # response_body itself is JSON text; decode/re-dump it too.
        body = record.get("response_body")
        if isinstance(body, str):
            try:
                record["response_body"] = dumps(json.loads(body))
            except json.JSONDecodeError:
                pass
        tmp.write(dumps(record))
tmp_path.replace(path)
print(f"rewrote {path}")
PY
```

Trailing newline in response body is
just how OpenAlex returned it.
