"""Public diff/cursor contract controls using the real managed world."""

import inspect

from proworksim import software_benchmark_world_v054 as module

from test_software_benchmark_world_v054 import bundle, call, prepare


def test_diff_public_parameters_execute_and_pages_cover_the_current_diff(tmp_path):
    prepared, port, _ = prepare(tmp_path)
    lines = [f"line-{i:03}: " + "content " * 16 + "\n" for i in range(100)]
    call(port, "write_file", path="main.py", text="".join(lines))
    schema = next(tool["parameters"] for tool in port.tools() if tool["name"] == "diff_workspace")
    assert set(schema["properties"]) == {"cursor"}
    assert not schema["required"] and schema["additionalProperties"] is False
    parameters = inspect.signature(prepared.world._action_diff_workspace).parameters
    assert set(schema["properties"]) <= set(parameters)

    first = call(port, "diff_workspace")
    assert first == call(port, "diff_workspace", cursor="")
    assert first == call(port, "diff_workspace", cursor=None)
    pages, page = [first["text"]], first
    while page["next_cursor"] is not None:
        following = call(port, "diff_workspace", cursor=page["next_cursor"])
        assert following["start_character"] == page["end_character"]
        assert following["source_reference"] == first["source_reference"]
        assert 0 < len(following["text"]) <= module.PAGE_CHARACTERS
        pages.append(following["text"])
        page = following
    text = "".join(pages)
    assert len(text) == page["total_characters"]
    assert "-value = 0\n" in text and all("+" + line in text for line in lines)
    assert module.digest(text.encode()) == first["text_sha256"]


def test_empty_cursor_is_first_page_for_all_repository_navigation(tmp_path):
    prepared, port, _ = prepare(tmp_path, extra_files=45)
    call(port, "write_file", path="main.py", text="first\nsecond\nthird\n")
    operations = [
        ("list_files", {}),
        ("read_file", {"path": "main.py", "start_line": 2}),
        ("search_file", {"path": "main.py", "text": "second"}),
        ("read_task", {}),
    ]
    for name, arguments in operations:
        expected = call(port, name, **arguments)
        assert call(port, name, cursor="", **arguments) == expected
        assert call(port, name, cursor=None, **arguments) == expected
    assert call(port, "read_file", path="main.py", start_line=2, cursor="")["text"].startswith("second\n")
    assert bundle(prepared)[2]["files"]["main.py"] == "first\nsecond\nthird\n"


def test_diff_rejects_cross_operation_stale_and_malformed_cursors(tmp_path):
    prepared, port, _ = prepare(tmp_path, extra_files=45)
    call(port, "write_file", path="main.py", text="changed\n" * 1000)
    first = call(port, "diff_workspace")
    assert first["next_cursor"]
    unrelated = call(port, "list_files")["next_cursor"]
    before = bundle(prepared)[1:]
    for cursor in (unrelated, " ", "bad-cursor", 0, False):
        assert not port.call("diff_workspace", cursor=cursor)["ok"]
        assert bundle(prepared)[1:] == before
    call(port, "write_file", path="main.py", text="edited again\n" * 1000)
    current = bundle(prepared)[1:]
    assert not port.call("diff_workspace", cursor=first["next_cursor"])["ok"]
    assert bundle(prepared)[1:] == current
    assert call(port, "diff_workspace", cursor="")["source_reference"] != first["source_reference"]


def test_diff_cannot_select_private_references_or_use_an_unregistered_executor(tmp_path):
    prepared, port, _ = prepare(tmp_path)
    before = bundle(prepared)[1:]
    for arguments in (
        {"offset": 0},
        {"max_chars": 6000},
        {"source_reference": {"object_id": "private-other-workspace", "version_id": "v1"}},
    ):
        response = port.call("diff_workspace", **arguments)
        assert not response["ok"]
        assert "not a public parameter" in str(response)
        assert "unexpected keyword" not in str(response)
        assert bundle(prepared)[1:] == before
    response = prepared.world.session("operator", module.PROJECT).call("diff_workspace")
    assert not response["ok"]
    assert "Only the one live registered member may act" in str(response)
    assert bundle(prepared)[1:] == before
