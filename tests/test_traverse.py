import pytest

from portmgr import portmgr


@pytest.fixture
def reset_globals():
    saved = list(portmgr.action_list)
    portmgr.action_list.clear()
    yield
    portmgr.action_list.clear()
    portmgr.action_list.extend(saved)


def make_leaf(directory):
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "docker-compose.yml").write_text("services: {}\n")


def test_traverse_collects_leaves(tmp_path, reset_globals):
    # root/dckrsub.yml -> [a, b]; each is a compose leaf
    make_leaf(tmp_path / "a")
    make_leaf(tmp_path / "b")
    (tmp_path / "dckrsub.yml").write_text("- a\n- b\n")

    portmgr.base_directory = str(tmp_path)
    portmgr.traverse(str(tmp_path))

    relatives = sorted(a["relative"] for a in portmgr.action_list)
    assert relatives == ["a", "b"]


def test_traverse_nested(tmp_path, reset_globals):
    # root -> group -> [x, y]
    (tmp_path / "dckrsub.yml").write_text("- group\n")
    (tmp_path / "group").mkdir()
    (tmp_path / "group" / "dckrsub.yml").write_text("- x\n- y\n")
    make_leaf(tmp_path / "group" / "x")
    make_leaf(tmp_path / "group" / "y")

    portmgr.base_directory = str(tmp_path)
    portmgr.traverse(str(tmp_path))

    relatives = sorted(a["relative"] for a in portmgr.action_list)
    assert relatives == ["group/x", "group/y"]


def test_add_command_dedupes(tmp_path, reset_globals):
    make_leaf(tmp_path / "a")
    portmgr.base_directory = str(tmp_path)

    portmgr.addCommand(str(tmp_path / "a"))
    portmgr.addCommand(str(tmp_path / "a"))

    assert len(portmgr.action_list) == 1


def test_addcommand_relative_dot_uses_basename(tmp_path, reset_globals):
    # When the target equals base_directory, relpath is '.', which is replaced
    # with the directory's basename.
    make_leaf(tmp_path / "stack")
    portmgr.base_directory = str(tmp_path / "stack")

    portmgr.addCommand(str(tmp_path / "stack"))

    assert portmgr.action_list[0]["relative"] == "stack"
