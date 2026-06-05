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

> [!CAUTION]
> Later deprecated
> in favour of batched title retrieval.

After some bug fixing,
the following run was produced
with batched title retrieval and a
command/query responsibility segregation-style
architecture:

- `tasks/tasks-20260602-oldest-papers/context/diagnostics/20260605_113204_mode1_v2_ssn_hit_v2_openalex_fixed`
for subset 1 and
- `tasks/tasks-20260602-oldest-papers/context/diagnostics/20260605_113859_mode2_v2_ssn_hit_v2_openalex_fixed`
for subset 2.

These seem to work fine
this time.

In particular,
I have compared
`repl_session.log` for
`tasks/tasks-20260526-match-patch/context/diagnostics/20260603_122743_mode2_v2_ssn_hit_v2_with_openalex` with
`tasks/tasks-20260602-oldest-papers/context/diagnostics/20260605_113859_mode2_v2_ssn_hit_v2_openalex_fixed`, and
it makes sense and
numbers are same.

Also,
I have compared a
known subset 2 listing:
<https://openalex.org/works?filter=authorships.author.id:A5049194901&include_xpac=true&sort=publication_year:asc>
on actual webpage and
in what `20260605_113859` produced
for `185_G_Philip_Robertson`.

Here is
what I received from OpenAlex:
out of 484 works,
here is the first page
(top oldest 10 works),
from older to newer;
number after venue and dash represents
cited by how many works:

-   [Untitled](https://openalex.org/works?filter=authorships.author.id:A5049194901&include_xpac=true&sort=publication_year:asc&zoom=w4231478824)

    1915 - George Armstrong, Charles Ball, et al. - British journal of surgery

-   [Masthead](https://openalex.org/works?filter=authorships.author.id:A5049194901&include_xpac=true&sort=publication_year:asc&zoom=w4214489755)

    1915 - George Armstrong, Charles Ball, et al. - British journal of surgery

-   [Polarographic determination of zinc in plant materials containing phosphate](https://openalex.org/works?filter=authorships.author.id:A5049194901&include_xpac=true&sort=publication_year:asc&zoom=w1991917775)

    1964 - G. Robertson - The Analyst - 1

-   [Time-of-flight atom-probe study of a W-Zr field emitter](https://openalex.org/works?filter=authorships.author.id:A5049194901&include_xpac=true&sort=publication_year:asc&zoom=w2076963006)

    1980 - Toshio Sakurai, Y. Kuk, et al. - Applied Physics Letters - 1

-   [Nitrification in the Course of Ecological Succession](https://openalex.org/works?filter=authorships.author.id:A5049194901&include_xpac=true&sort=publication_year:asc&zoom=w2018220247)

    1981 - G. Philip Robertson, Peter M. Vitousek - BioScience - 2

-   [Nitrification Potentials in Primary and Secondary Succession](https://openalex.org/works?filter=authorships.author.id:A5049194901&include_xpac=true&sort=publication_year:asc&zoom=w2106351560)

    1981 - G. Philip Robertson, Peter M. Vitousek - Ecology - 298

-   [Nitrogen Cycling in Ecosystems of Latin America and the Caribbean](https://openalex.org/works?filter=authorships.author.id:A5049194901&include_xpac=true&sort=publication_year:asc&zoom=w2273198649)

    1982 - G. P. Robertson, R. Herrera, et al. - 23

-   [Regional nitrogen budgets: Approaches and problems](https://openalex.org/works?filter=authorships.author.id:A5049194901&include_xpac=true&sort=publication_year:asc&zoom=w2149268153)

    1982 - G. P. Robertson - 13

-   [Los balances regionales de nitrògeno : Enfoques y problemas](https://openalex.org/works?filter=authorships.author.id:A5049194901&include_xpac=true&sort=publication_year:asc&zoom=w95866080)

    1982 - G. Philip Robertson

-   [Nitrification in forested ecosystems](https://openalex.org/works?filter=authorships.author.id:A5049194901&include_xpac=true&sort=publication_year:asc&zoom=w2101363828)

    1982 - G. P. Robertson - Philosophical transactions of the Royal Society of London. Series B, Biological sciences - 212

And here is
what is in the card:

```
**ktp.ssn_top_oldest_papers**: [{"ssnp.date":"1964-01-01","openalex.title":"Polarographic determination of zinc in plant materials containing phosphate","ktp.ssnp_paperid_url":"https://openalex.org/W1991917775"}, {"ssnp.date":"1980-05-15","openalex.title":"Time-of-flight atom-probe study of a W-Zr field emitter","ktp.ssnp_paperid_url":"https://openalex.org/W2076963006"}, {"ssnp.date":"1981-02-01","openalex.title":"Nitrification in the Course of Ecological Succession","ktp.ssnp_paperid_url":"https://openalex.org/W2018220247"}, {"ssnp.date":"1981-04-01","openalex.title":"Nitrification Potentials in Primary and Secondary Succession","ktp.ssnp_paperid_url":"https://openalex.org/W2106351560"}, {"ssnp.date":"1982-01-01","openalex.title":"Regional nitrogen budgets: Approaches and problems","ktp.ssnp_paperid_url":"https://openalex.org/W2149268153"}]
```

So this generally aligns,
except:

- Untitled
- Masthead
- Nitrogen Cycling in Ecosystems of Latin America and the Caribbean

I confirmed that
the first two are absent
from SciSciNet-v2 papers parquet.

The third one is
a date tie with card’s
Regional nitrogen budgets: Approaches and problems
at 1982-01-01, and
it is resolved as expected
in the card, with
W2149268153 coming before
W2273198649, while
on OpenAlex
for whatever reason
this is implemented differently;
not an issue.

Therefore,
this seems to be
working as expected.
