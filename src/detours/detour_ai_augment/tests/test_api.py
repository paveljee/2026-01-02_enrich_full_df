from __future__ import annotations

import hashlib
import html
import json
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from src.detours.detour_ai_augment.src.backend import api

ROLLOUT_GUEST_PATH = "/home/ai/.codex/sessions/2026/07/31/rollout-chat.jsonl"
ROLLOUT_RELATIVE_PATH = PurePosixPath("2026/07/31/rollout-chat.jsonl")
EVIDENCE_TEXT = "Professor Example holds the Example Chair."
SAMPLE_SESSIONS = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "sample_run"
    / ".codex"
    / "sessions"
)


def rollout_record(value: Mapping[str, object], line_number: int) -> api.RolloutRecord:
    raw_line = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode() + b"\n"
    return api.RolloutRecord(
        line_number=line_number,
        line_sha256=hashlib.sha256(raw_line).hexdigest(),
        value=dict(value),
    )


def web_records(
    action: str = "search_query",
    *,
    call_id: str = "call_example",
    output: object | None = None,
) -> tuple[api.RolloutRecord, ...]:
    call = {
        "type": "response_item",
        "payload": {
            "type": "function_call",
            "namespace": "web",
            "name": "run",
            "arguments": json.dumps({action: [{"q": "example"}]}),
            "call_id": call_id,
        },
    }
    event = {
        "type": "event_msg",
        "payload": {
            "type": "web_search_end",
            "call_id": call_id,
            "query": "example",
        },
    }
    result = {
        "type": "response_item",
        "payload": {
            "type": "function_call_output",
            "call_id": call_id,
            "output": (
                [{"type": "input_text", "text": EVIDENCE_TEXT}]
                if output is None
                else output
            ),
        },
    }
    return (
        rollout_record(call, 1),
        rollout_record(event, 2),
        rollout_record(result, 3),
    )


def submission_body(excerpt: str = EVIDENCE_TEXT) -> dict[str, object]:
    return {
        column: {
            "value": f"answer for {column}",
            "web_search_excerpts": [excerpt],
        }
        for column in api.COLUMNS
    }


def valid_report() -> str:
    return (
        ".\n"
        "└── 2026/\n"
        "    └── 07/\n"
        "        └── 31/\n"
        f"            └── {api.APPENDWATCH_OK_PREFIX}rollout-chat.jsonl\n"
    )


def bundled_sample_rollout() -> Path:
    rollout_paths = tuple(SAMPLE_SESSIONS.rglob("rollout-*.jsonl"))
    assert len(rollout_paths) == 1
    return rollout_paths[0]


def report_for_rollout(relative_path: PurePosixPath) -> str:
    lines = ["."]
    for depth, part in enumerate(relative_path.parts):
        prefix = "    " * depth + "└── "
        lines.append(
            prefix
            + (
                f"{api.APPENDWATCH_OK_PREFIX}{part}"
                if part == relative_path.name
                else f"{part}/"
            )
        )
    return "\n".join(lines) + "\n"


def configured(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> api.PushConfiguration:
    report = tmp_path / "appendwatch-tree.txt"
    identity = tmp_path / "id_ed25519"
    known_hosts = tmp_path / "known_hosts"
    lima_config = tmp_path / "ssh.config"
    report.write_text(valid_report(), encoding="utf-8")
    for path in (identity, known_hosts, lima_config):
        path.write_text("fixture\n", encoding="utf-8")

    monkeypatch.setattr(api, "ROLLOUT_JSONL", ROLLOUT_GUEST_PATH)
    monkeypatch.setattr(api, "APPENDWATCH_REPORT", report)
    monkeypatch.setattr(api, "AIVM_IDENTITY_FILE", identity)
    monkeypatch.setattr(api, "AIVM_KNOWN_HOSTS_FILE", known_hosts)
    monkeypatch.setattr(api, "LIMA_SSH_CONFIG_PATH", lima_config)
    return api.push_configuration()


@pytest.mark.parametrize("action", sorted(api.ELIGIBLE_WEB_ACTIONS))
def test_search_open_and_click_are_eligible(action: str) -> None:
    index = api.build_evidence_index(web_records(action))

    matches = index.matches("Example Chair")

    assert len(matches) == 1
    assert matches[0].call_id == "call_example"
    assert matches[0].events[0].value["payload"]["type"] == "web_search_end"  # type: ignore[index]


def test_bundled_sample_rollout_uses_supported_real_web_schema() -> None:
    records = api.parse_rollout(bundled_sample_rollout())
    index = api.build_evidence_index(records)
    actions: set[str] = set()

    assert records
    assert index.pairs
    for pair in index.pairs:
        payload = pair.call.value["payload"]
        assert isinstance(payload, dict)
        arguments = payload["arguments"]
        assert isinstance(arguments, str)
        actions.update(set(json.loads(arguments)) & api.ELIGIBLE_WEB_ACTIONS)
        complete_text = next(text for text in pair.text_blocks if text)
        assert pair in index.matches(complete_text)

    assert actions == api.ELIGIBLE_WEB_ACTIONS


def independently_link_sample_web_pairs(sample_rollout: Path) -> tuple[SimpleNamespace, ...]:
    calls: list[SimpleNamespace] = []
    outputs: dict[str, list[SimpleNamespace]] = {}
    events: dict[str, list[SimpleNamespace]] = {}

    for line_number, raw_line in enumerate(
        sample_rollout.read_bytes().splitlines(keepends=True),
        start=1,
    ):
        value = json.loads(raw_line)
        assert isinstance(value, dict)
        record = SimpleNamespace(
            line_number=line_number,
            line_sha256=hashlib.sha256(raw_line).hexdigest(),
            value=value,
        )
        payload = value.get("payload")
        if not isinstance(payload, dict):
            continue
        if (
            value.get("type") == "response_item"
            and payload.get("type") == "function_call"
            and payload.get("namespace") == "web"
            and payload.get("name") == "run"
        ):
            call_id = payload.get("call_id")
            arguments = payload.get("arguments")
            assert isinstance(call_id, str) and call_id
            assert isinstance(arguments, str)
            decoded_arguments = json.loads(arguments)
            assert isinstance(decoded_arguments, dict)
            if set(decoded_arguments) & api.ELIGIBLE_WEB_ACTIONS:
                calls.append(SimpleNamespace(call_id=call_id, record=record))
        elif (
            value.get("type") == "response_item"
            and payload.get("type") == "function_call_output"
        ):
            call_id = payload.get("call_id")
            assert isinstance(call_id, str) and call_id
            outputs.setdefault(call_id, []).append(record)
        elif value.get("type") == "event_msg" and payload.get("type") == "web_search_end":
            call_id = payload.get("call_id")
            assert isinstance(call_id, str) and call_id
            events.setdefault(call_id, []).append(record)

    pairs: list[SimpleNamespace] = []
    for call in calls:
        matching_outputs = outputs[call.call_id]
        assert len(matching_outputs) == 1
        output_record = matching_outputs[0]
        output_payload = output_record.value["payload"]["output"]
        if isinstance(output_payload, str):
            text_blocks = (output_payload,)
        else:
            assert isinstance(output_payload, list) and output_payload
            assert all(
                isinstance(block, dict)
                and block.get("type") == "input_text"
                and isinstance(block.get("text"), str)
                for block in output_payload
            )
            text_blocks = tuple(block["text"] for block in output_payload)
        pairs.append(
            SimpleNamespace(
                call_id=call.call_id,
                call=call.record,
                output=output_record,
                events=tuple(events.get(call.call_id, [])),
                text_blocks=text_blocks,
            )
        )
    return tuple(pairs)


def prepare_real_sample_push(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> SimpleNamespace:
    sample_rollout = bundled_sample_rollout()
    host_relative = sample_rollout.relative_to(SAMPLE_SESSIONS)
    rollout_relative = PurePosixPath(*host_relative.parts)
    rollout_guest_path = f"{api.CODEX_SESSIONS_ROOT}/{rollout_relative}"
    deployment = tmp_path / "deployment"
    deployment.mkdir()
    report = deployment / "appendwatch-tree.txt"
    identity = deployment / "id_ed25519"
    known_hosts = deployment / "known_hosts"
    lima_config = deployment / "ssh.config"
    report.write_text(report_for_rollout(rollout_relative), encoding="utf-8")
    for path in (identity, known_hosts, lima_config):
        path.write_text("fixture\n", encoding="utf-8")

    attempts = tmp_path / "attempts"
    monkeypatch.setattr(api, "ROLLOUT_JSONL", rollout_guest_path)
    monkeypatch.setattr(api, "APPENDWATCH_REPORT", report)
    monkeypatch.setattr(api, "AIVM_IDENTITY_FILE", identity)
    monkeypatch.setattr(api, "AIVM_KNOWN_HOSTS_FILE", known_hosts)
    monkeypatch.setattr(api, "LIMA_SSH_CONFIG_PATH", lima_config)
    monkeypatch.setattr(api, "ATTEMPTS_DIR", attempts)

    def fake_scp(command: list[str], **_kwargs: object) -> None:
        assert command[-2].endswith(f":{rollout_guest_path}")
        Path(command[-1]).write_bytes(sample_rollout.read_bytes())

    monkeypatch.setattr(api.subprocess, "run", fake_scp)

    expected_pairs = independently_link_sample_web_pairs(sample_rollout)
    assert len(expected_pairs) == len(api.COLUMNS)
    payload: dict[str, object] = {}
    expected_evidence: dict[str, tuple[str, SimpleNamespace]] = {}
    for column, pair in zip(api.COLUMNS, expected_pairs, strict=True):
        candidates = [
            line
            for text_block in pair.text_blocks
            for line in text_block.splitlines()
            if line.strip()
        ] + list(pair.text_blocks)
        excerpt = next(
            candidate
            for candidate in candidates
            if tuple(
                candidate_pair
                for candidate_pair in expected_pairs
                if any(candidate in text for text in candidate_pair.text_blocks)
            )
            == (pair,)
        )
        payload[column] = {
            "value": f"synthetic answer for {column}",
            "web_search_excerpts": [excerpt],
        }
        expected_evidence[column] = (excerpt, pair)

    eligible_lines = {
        record.line_number
        for pair in expected_pairs
        for record in (pair.call, pair.output, *pair.events)
    }
    unrelated_record = next(
        SimpleNamespace(
            line_number=line_number,
            line_sha256=hashlib.sha256(raw_line).hexdigest(),
            value=value,
        )
        for line_number, raw_line in enumerate(
            sample_rollout.read_bytes().splitlines(keepends=True),
            start=1,
        )
        if (value := json.loads(raw_line)).get("type") == "response_item"
        and line_number not in eligible_lines
    )

    return SimpleNamespace(
        client=TestClient(api.app),
        payload=payload,
        attempts=attempts,
        sample_rollout=sample_rollout,
        report=report,
        expected_evidence=expected_evidence,
        unrelated_record=unrelated_record,
        truth={column: f"synthetic truth for {column}" for column in api.COLUMNS},
    )


def test_exact_excerpt_matching_does_not_normalize_or_join_blocks() -> None:
    text = "café  Example\nChair"
    index = api.build_evidence_index(
        web_records(output=[{"type": "input_text", "text": text}])
    )
    split_index = api.build_evidence_index(
        web_records(
            output=[
                {"type": "input_text", "text": "café  Example"},
                {"type": "input_text", "text": "Chair"},
            ]
        )
    )

    assert index.matches("café  Example\nChair")
    assert not index.matches("cafe  Example\nChair")
    assert not index.matches("café Example\nChair")
    assert not split_index.matches("ExampleChair")


def test_non_web_and_orphan_text_is_not_eligible() -> None:
    records = (
        rollout_record(
            {
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": EVIDENCE_TEXT}],
                },
            },
            1,
        ),
        rollout_record(
            {
                "type": "response_item",
                "payload": {
                    "type": "reasoning",
                    "summary": [{"type": "summary_text", "text": EVIDENCE_TEXT}],
                },
            },
            2,
        ),
        rollout_record(
            {
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "name": "exec_command",
                    "arguments": "{}",
                    "call_id": "shell_call",
                },
            },
            3,
        ),
        rollout_record(
            {
                "type": "response_item",
                "payload": {
                    "type": "function_call_output",
                    "call_id": "orphan_call",
                    "output": EVIDENCE_TEXT,
                },
            },
            4,
        ),
        rollout_record(
            {
                "type": "event_msg",
                "payload": {
                    "type": "web_search_end",
                    "call_id": "event_only",
                    "query": EVIDENCE_TEXT,
                },
            },
            5,
        ),
    )

    assert not api.build_evidence_index(records).matches(EVIDENCE_TEXT)


def test_duplicate_ids_and_unsupported_outputs_fail_closed() -> None:
    call, _event, output = web_records()

    with pytest.raises(api.PushValidationError, match="duplicate web call_id"):
        api.build_evidence_index((call, call, output))
    with pytest.raises(api.PushValidationError, match="duplicate function output"):
        api.build_evidence_index((call, output, output))
    unsupported = web_records(output=[{"type": "output_text", "text": EVIDENCE_TEXT}])
    with pytest.raises(api.PushValidationError, match="unsupported text block"):
        api.build_evidence_index(unsupported)


def test_rollout_parser_rejects_completed_malformed_json_but_ignores_live_tail(
    tmp_path: Path,
) -> None:
    rollout = tmp_path / "rollout.jsonl"
    rollout.write_bytes(b'{"type":"event_msg"}\n{"incomplete"')
    assert len(api.parse_rollout(rollout)) == 1

    rollout.write_bytes(b'{"type":"event_msg"}\nnot-json\n')
    with pytest.raises(api.PushValidationError, match="line 2"):
        api.parse_rollout(rollout)


def test_submission_requires_exact_outer_and_inner_contract() -> None:
    index = api.build_evidence_index(web_records())
    body = submission_body()
    validated: api.ValidatedEvidence = {}

    parsed = api.Submission.model_validate(
        body,
        context={"evidence_index": index, "validated_evidence": validated},
    )

    assert tuple(parsed.root) == api.COLUMNS
    assert set(validated) == set(api.COLUMNS)

    missing = dict(body)
    missing.pop(api.COLUMNS[0])
    with pytest.raises(ValidationError):
        api.Submission.model_validate(
            missing,
            context={"evidence_index": index, "validated_evidence": {}},
        )

    extra_inner = json.loads(json.dumps(body))
    extra_inner[api.COLUMNS[0]]["unexpected"] = True
    with pytest.raises(ValidationError):
        api.Submission.model_validate(
            extra_inner,
            context={"evidence_index": index, "validated_evidence": {}},
        )

    null_value = json.loads(json.dumps(body))
    null_value[api.COLUMNS[0]]["value"] = None
    with pytest.raises(ValidationError):
        api.Submission.model_validate(
            null_value,
            context={"evidence_index": index, "validated_evidence": {}},
        )

    duplicate_excerpt = json.loads(json.dumps(body))
    duplicate_excerpt[api.COLUMNS[0]]["web_search_excerpts"] *= 2
    with pytest.raises(ValidationError):
        api.Submission.model_validate(
            duplicate_excerpt,
            context={"evidence_index": index, "validated_evidence": {}},
        )

    absent_excerpt = json.loads(json.dumps(body))
    absent_excerpt[api.COLUMNS[0]]["web_search_excerpts"] = []
    with pytest.raises(ValidationError):
        api.Submission.model_validate(
            absent_excerpt,
            context={"evidence_index": index, "validated_evidence": {}},
        )


def test_copied_report_requires_one_nested_ok_path(tmp_path: Path) -> None:
    report = tmp_path / "snapshot.txt"
    report.write_text(valid_report(), encoding="utf-8")

    api.parse_appendwatch_report(report, ROLLOUT_RELATIVE_PATH)


@pytest.mark.parametrize(
    "report",
    [
        ".  [COMPROMISED: monitoring gap]\n",
        (
            ".\n"
            "└── 2026/\n"
            "    └── COMPROMISED 07/  [monitoring gap]\n"
            "        └── 31/\n"
            f"            └── {api.APPENDWATCH_OK_PREFIX}rollout-chat.jsonl\n"
        ),
        (
            ".\n"
            "└── 2026/\n"
            "    └── 07/\n"
            "        └── 31/\n"
            f"            └── {api.APPENDWATCH_COMPROMISED_PREFIX}"
            "rollout-chat.jsonl  [modified]\n"
        ),
        ".\n└── malformed status rollout-chat.jsonl\n",
        ".\n",
        (
            ".\n"
            "└── 2026/\n"
            "    └── 07/\n"
            "        └── 31/\n"
            f"            ├── {api.APPENDWATCH_OK_PREFIX}rollout-chat.jsonl\n"
            f"            └── {api.APPENDWATCH_OK_PREFIX}rollout-chat.jsonl\n"
        ),
        (
            ".\n"
            "\n"
            "removed or replaced (no longer a regular file):\n"
            f"    {api.APPENDWATCH_COMPROMISED_PREFIX}"
            "2026/07/31/rollout-chat.jsonl  [removed]\n"
        ),
    ],
)
def test_copied_report_fails_closed(report: str, tmp_path: Path) -> None:
    snapshot = tmp_path / "snapshot.txt"
    snapshot.write_text(report, encoding="utf-8")

    with pytest.raises(api.PushValidationError):
        api.parse_appendwatch_report(snapshot, ROLLOUT_RELATIVE_PATH)


@pytest.mark.parametrize(
    "rollout",
    [
        "",
        "relative/rollout-chat.jsonl",
        "/home/ai/.codex/sessions/../rollout-chat.jsonl",
        "/home/ai/rollout-chat.jsonl",
        "/home/ai/.codex/sessions/2026/07/31/not-a-rollout.txt",
        "/home/ai/.codex/sessions/2026/07/31/rollout-chat.jsonl\n",
    ],
)
def test_rollout_configuration_is_confined(
    rollout: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(api, "ROLLOUT_JSONL", rollout)

    with pytest.raises(api.PushConfigurationError):
        api.push_configuration()


def test_scp_uses_dedicated_pinned_connection_and_atomic_archive(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configuration = configured(tmp_path, monkeypatch)
    attempt_dir = tmp_path / "attempt"
    attempt_dir.mkdir()
    captured: dict[str, Any] = {}

    def fake_run(command: list[str], **kwargs: object) -> None:
        captured["command"] = command
        captured["kwargs"] = kwargs
        Path(command[-1]).write_bytes(b"rollout bytes\n")

    monkeypatch.setattr(api.subprocess, "run", fake_run)

    archived = api.copy_rollout(configuration, attempt_dir, "attempt-id")

    command = captured["command"]
    assert command[0] == "scp"
    assert f"IdentityFile={configuration.identity_file}" in command
    assert f"UserKnownHostsFile={configuration.known_hosts_file}" in command
    assert f"HostKeyAlias={configuration.host_key_alias}" in command
    assert "StrictHostKeyChecking=accept-new" in command
    assert command[-2] == f"{configuration.ssh_target}:{ROLLOUT_GUEST_PATH}"
    assert "shell" not in captured["kwargs"]
    assert archived.path.name == "rollout.attempt-id.jsonl"
    assert archived.sha256 == hashlib.sha256(b"rollout bytes\n").hexdigest()
    assert not (attempt_dir / ".rollout.tmp").exists()


def fake_artifact(path: Path, value: bytes) -> api.ArchivedFile:
    path.write_bytes(value)
    return api.ArchivedFile(
        path=path,
        size=len(value),
        sha256=hashlib.sha256(value).hexdigest(),
    )


def test_push_runs_integrity_gate_in_exact_order(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    attempt_dir = tmp_path / "attempt"
    configuration = api.PushConfiguration(
        rollout_guest_path=ROLLOUT_GUEST_PATH,
        rollout_relative_path=ROLLOUT_RELATIVE_PATH,
        appendwatch_report=tmp_path / "live-report",
        lima_ssh_config=tmp_path / "ssh.config",
        identity_file=tmp_path / "identity",
        known_hosts_file=tmp_path / "known-hosts",
        ssh_target="aivm-ai",
        host_key_alias="lima-aivm-ai",
    )

    def fake_configuration() -> api.PushConfiguration:
        events.append("configuration")
        return configuration

    def fake_create(_attempt_id: str) -> Path:
        attempt_dir.mkdir()
        return attempt_dir

    def fake_rollout(
        _configuration: api.PushConfiguration,
        directory: Path,
        _attempt_id: str,
    ) -> api.ArchivedFile:
        events.append("scp")
        return fake_artifact(directory / "rollout.jsonl", b"rollout\n")

    def fake_report(
        _configuration: api.PushConfiguration,
        directory: Path,
        _attempt_id: str,
    ) -> api.ArchivedFile:
        events.append("status_copy")
        return fake_artifact(directory / "report.txt", b".\n")

    def fake_pydantic(
        _cls: type[api.Submission],
        _body: bytes,
        *,
        context: dict[str, object],
    ) -> object:
        events.append("pydantic")
        validated_evidence = context["validated_evidence"]
        assert isinstance(validated_evidence, dict)
        validated_evidence.update({column: [] for column in api.COLUMNS})
        return SimpleNamespace(
            root={
                column: SimpleNamespace(value=f"answer for {column}")
                for column in api.COLUMNS
            }
        )

    def fake_status_check(*_args: object) -> None:
        events.append("status_check")

    def fake_rollout_parse(*_args: object) -> tuple[api.RolloutRecord, ...]:
        events.append("rollout_parse")
        return ()

    def fake_evidence_index(*_args: object) -> api.EvidenceIndex:
        events.append("evidence_index")
        return api.EvidenceIndex(())

    def fake_ground_truth() -> dict[str, object]:
        events.append("ground_truth")
        return {column: f"truth for {column}" for column in api.COLUMNS}

    def fake_dump(*_args: object, **_kwargs: object) -> tuple[str, str]:
        events.append("dump")
        return "submitted\n", "truth\n"

    monkeypatch.setattr(api, "push_configuration", fake_configuration)
    monkeypatch.setattr(api, "create_attempt", fake_create)
    monkeypatch.setattr(api, "record_attempt", lambda *args, **kwargs: None)
    monkeypatch.setattr(api, "copy_rollout", fake_rollout)
    monkeypatch.setattr(api, "copy_appendwatch_report", fake_report)
    monkeypatch.setattr(api, "parse_appendwatch_report", fake_status_check)
    monkeypatch.setattr(api, "parse_rollout", fake_rollout_parse)
    monkeypatch.setattr(api, "build_evidence_index", fake_evidence_index)
    monkeypatch.setattr(
        api.Submission,
        "model_validate_json",
        classmethod(fake_pydantic),
    )
    monkeypatch.setattr(api, "ground_truth", fake_ground_truth)
    monkeypatch.setattr(api, "dump_push", fake_dump)

    response = TestClient(api.app).post("/push", json=submission_body())

    assert response.status_code == 200
    assert events == [
        "configuration",
        "scp",
        "status_copy",
        "status_check",
        "rollout_parse",
        "evidence_index",
        "pydantic",
        "ground_truth",
        "dump",
    ]


def test_real_sample_exact_excerpts_render_linked_objects_end_to_end(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = prepare_real_sample_push(tmp_path, monkeypatch)
    monkeypatch.setattr(api, "ground_truth", lambda: context.truth)

    response = context.client.post("/push", json=context.payload)

    assert response.status_code == 200
    response_lines = response.text.splitlines()
    assert len(response_lines) == 2
    assert json.loads(response_lines[0]) == {
        column: context.payload[column]["value"]
        for column in api.COLUMNS
    }
    assert json.loads(response_lines[1]) == context.truth

    attempt_dir = next(context.attempts.iterdir())
    attempt = json.loads((attempt_dir / "attempt.json").read_text(encoding="utf-8"))
    assert attempt["result"] == "accepted"
    rollout_archive = next(attempt_dir.glob("rollout.*.jsonl"))
    report_archive = next(attempt_dir.glob("appendwatch-tree.*.txt"))
    assert rollout_archive.read_bytes() == context.sample_rollout.read_bytes()
    assert report_archive.read_bytes() == context.report.read_bytes()
    assert (attempt_dir / "response.jsonl").is_file()
    markdown = (attempt_dir / "response.md").read_text(encoding="utf-8")

    def escaped_json(value: object) -> str:
        return html.escape(json.dumps(value, ensure_ascii=False, indent=2))

    assert attempt["artifacts"]["rollout"]["sha256"] in markdown
    assert attempt["artifacts"]["appendwatch_report"]["sha256"] in markdown
    assert markdown.count("<details>") == len(api.COLUMNS)
    for column_index, column in enumerate(api.COLUMNS):
        section_start = markdown.index(f"## {column}\n")
        section_end = (
            markdown.index(f"## {api.COLUMNS[column_index + 1]}\n")
            if column_index + 1 < len(api.COLUMNS)
            else len(markdown)
        )
        section = markdown[section_start:section_end]
        excerpt, pair = context.expected_evidence[column]

        assert f"<pre><code>{html.escape(excerpt)}</code></pre>" in section
        assert escaped_json(context.payload[column]["value"]) in section
        assert escaped_json(context.truth[column]) in section
        assert escaped_json(pair.call.value) in section
        assert escaped_json(pair.output.value) in section
        assert pair.call.line_sha256 in section
        assert pair.output.line_sha256 in section
        for event in pair.events:
            assert escaped_json(event.value) in section
            assert event.line_sha256 in section

        assert markdown.count(escaped_json(pair.call.value)) == 1
        assert markdown.count(escaped_json(pair.output.value)) == 1

    assert escaped_json(context.unrelated_record.value) not in markdown


def test_real_sample_rollout_rejects_non_exact_excerpt_before_ground_truth(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = prepare_real_sample_push(tmp_path, monkeypatch)
    payload = json.loads(json.dumps(context.payload))
    payload[api.COLUMNS[0]]["web_search_excerpts"][0] += " text absent from rollout"
    monkeypatch.setattr(
        api,
        "ground_truth",
        lambda: pytest.fail("ground truth must not be loaded after rejection"),
    )

    response = context.client.post("/push", json=payload)

    assert response.status_code == 422
    assert response.json() == {"detail": api.VALIDATION_ERROR_DETAIL}
    attempt_dir = next(context.attempts.iterdir())
    attempt = json.loads((attempt_dir / "attempt.json").read_text(encoding="utf-8"))
    assert attempt["result"] == "rejected"
    assert not (attempt_dir / "response.jsonl").exists()
    assert not (attempt_dir / "response.md").exists()


def test_missing_rollout_is_generic_503_and_pull_still_works(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    source = tmp_path / "source.jsonl"
    source.write_text(
        json.dumps(
            {
                api.DRAW_NUMBER_COLUMN: api.TARGET_DRAW_NUMBER,
                api.FRAGMENT_TYPE_COLUMN: api.DOCX_ROW_FRAGMENT_TYPE,
                **dict.fromkeys(api.COLUMNS),
            }
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(api, "SOURCE_FILE", source)
    monkeypatch.setattr(api, "ROLLOUT_JSONL", "")
    client = TestClient(api.app)

    push_response = client.post("/push", json={})
    pull_response = client.get("/pull")

    assert push_response.status_code == 503
    assert push_response.json() == {"detail": api.CONFIGURATION_ERROR_DETAIL}
    assert api.ROLLOUT_ENV_NAME in caplog.text
    assert pull_response.status_code == 200
    assert json.loads(pull_response.text) == dict.fromkeys(api.COLUMNS)


def test_validation_failure_is_generic_and_creates_no_accepted_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    configuration = configured(tmp_path, monkeypatch)
    attempts = tmp_path / "attempts"
    monkeypatch.setattr(api, "ATTEMPTS_DIR", attempts)
    monkeypatch.setattr(api, "push_configuration", lambda: configuration)
    monkeypatch.setattr(
        api,
        "copy_rollout",
        lambda _config, directory, _attempt_id: fake_artifact(
            directory / "rollout.jsonl", b"{}\n"
        ),
    )
    monkeypatch.setattr(
        api,
        "copy_appendwatch_report",
        lambda _config, directory, _attempt_id: fake_artifact(
            directory / "report.txt", valid_report().encode()
        ),
    )
    monkeypatch.setattr(api, "parse_appendwatch_report", lambda *args: None)
    monkeypatch.setattr(api, "parse_rollout", lambda *args: ())
    monkeypatch.setattr(
        api,
        "ground_truth",
        lambda: pytest.fail("ground truth must not be loaded after rejection"),
    )

    response = TestClient(api.app).post("/push", json=submission_body())

    assert response.status_code == 422
    assert response.json() == {"detail": api.VALIDATION_ERROR_DETAIL}
    attempt_dir = next(attempts.iterdir())
    assert not (attempt_dir / "response.jsonl").exists()
    assert not (attempt_dir / "response.md").exists()
    assert api.COLUMNS[0] in caplog.text


def test_openapi_does_not_disclose_integrity_internals() -> None:
    schema = TestClient(api.app).get("/openapi.json").json()
    push_schema = schema["paths"]["/push"]["post"]
    serialized = json.dumps(push_schema).lower()

    assert push_schema["description"] == "Validates and stores the completed submission."
    assert "appendwatch" not in serialized
    assert "rollout" not in serialized
    assert api.ROLLOUT_ENV_NAME.lower() not in serialized


def test_report_contains_complete_deduplicated_escaped_evidence(
    tmp_path: Path,
) -> None:
    malicious = "Evidence </code><script>alert('x')</script>"
    records = web_records(output=malicious)
    pair = api.build_evidence_index(records).pairs[0]
    evidence: api.ValidatedEvidence = {
        column: [(malicious, (pair,))]
        for column in api.COLUMNS
    }
    submission = {column: f"answer <{column}>" for column in api.COLUMNS}
    truth = {column: f"truth <{column}>" for column in api.COLUMNS}
    rollout = fake_artifact(tmp_path / "rollout.jsonl", b"rollout\n")
    report = fake_artifact(tmp_path / "appendwatch.txt", b".\n")

    lines = api.dump_push(
        submission,
        truth,
        output_dir=tmp_path,
        evidence=evidence,
        rollout_archive=rollout,
        report_archive=report,
    )

    markdown = (tmp_path / "response.md").read_text(encoding="utf-8")
    assert markdown.count("<details>") == 1
    assert "<script>" not in markdown
    assert "&lt;script&gt;" in markdown
    assert html.escape(
        json.dumps(pair.call.value, ensure_ascii=False, indent=2)
    ) in markdown
    assert html.escape(
        json.dumps(pair.output.value, ensure_ascii=False, indent=2)
    ) in markdown
    assert rollout.sha256 in markdown
    assert report.sha256 in markdown
    assert all(f"## {column}" in markdown for column in api.COLUMNS)
    assert (tmp_path / "response.jsonl").read_text(encoding="utf-8") == "".join(lines)
    assert len((tmp_path / "response.jsonl").read_text().splitlines()) == 2
