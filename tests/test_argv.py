import pytest

from portmgr.portmgr import ArgvError, HelpRequested, split_argv

# A stand-in for command_list: the real letters, and which of them take arguments.
COMMANDS = {c: {} for c in "upsdlabctrvoSMR"}
COMMANDS["E"] = {"args": True}
COMMANDS["D"] = {"args": ("--force",)}


@pytest.mark.parametrize("argv, expected", [
    ("pul", ("", ["p", "u", "l"], [])),
    ("-pul", ("", ["p", "u", "l"], [])),
    ("-p -u -l", ("", ["p", "u", "l"], [])),
    ("-pu -l", ("", ["p", "u", "l"], [])),
    ("pu -l", ("", ["p", "u", "l"], [])),
    ("E pass", ("", ["E"], ["pass"])),
    ("-E pass", ("", ["E"], ["pass"])),
    ("uE pass", ("", ["u", "E"], ["pass"])),
    ("E dup u", ("", ["E"], ["dup", "u"])),
    ("E pass -u", ("", ["E"], ["pass", "-u"])),
    ("E .env", ("", ["E"], [".env"])),
    ("E -- -u", ("", ["E"], ["-u"])),
    ("D --force", ("", ["D"], ["--force"])),
    ("D", ("", ["D"], [])),
    ("-B /x u", ("/x", ["u"], [])),
    ("u -B /x", ("/x", ["u"], [])),
    ("-B /x E pass", ("/x", ["E"], ["pass"])),
    ("-B/x u", ("/x", ["u"], [])),
    ("-B ul u", ("ul", ["u"], [])),
    ("S", ("", ["S"], [])),
    ("", ("", [], [])),
    ("-B /x", ("/x", [], [])),
])
def test_accepted(argv, expected):
    assert split_argv(argv.split(), COMMANDS) == expected


@pytest.mark.parametrize("argv, message", [
    ("pu l", "unexpected argument 'l'"),
    ("-pu l", "unexpected argument 'l'"),
    ("-p -u l", "unexpected argument 'l'"),
    ("l db", "unexpected argument 'db'"),
    ("u wiki", "unexpected argument 'wiki'"),
    ("S d", "unexpected argument 'd'"),
    ("u --foo", "unexpected argument '--foo'"),
    ("--force D", "unexpected argument '--force'"),
    ("D -x", "unknown command 'x'"),
    ("D x", "D takes only '--force', not 'x'"),
    ("xyz", "unknown command 'x'"),
    ("-uz", "unknown command 'z'"),
    ("uz", "unknown command 'z'"),
    ("u -B", "-B needs a directory"),
])
def test_rejected(argv, message):
    with pytest.raises(ArgvError) as exc:
        split_argv(argv.split(), COMMANDS)
    assert message in str(exc.value)


def test_unexpected_argument_hint():
    with pytest.raises(ArgvError) as exc:
        split_argv(["pu", "l"], COMMANDS)
    assert str(exc.value) == (
        "unexpected argument 'l': combine commands as 'pul', '-p -u -l' or 'pu -l'"
    )


@pytest.mark.parametrize("argv", ["-h", "--help", "u -h", "-B /x --help"])
def test_help(argv):
    with pytest.raises(HelpRequested):
        split_argv(argv.split(), COMMANDS)


def test_help_after_arguments_is_an_argument():
    # Once the arguments start, nothing is an option any more.
    assert split_argv(["E", "pass", "-h"], COMMANDS) == ("", ["E"], ["pass", "-h"])
