from portmgr.portmgr import normalize_argv

# A minimal stand-in for command_list (only membership matters).
COMMANDS = {"u": {}, "d": {}, "l": {}, "m": {}}


def test_single_letter_becomes_flag():
    assert normalize_argv(["u"], COMMANDS) == ["-u"]


def test_multiple_letters_become_single_flag():
    assert normalize_argv(["dul"], COMMANDS) == ["-dul"]


def test_d_value_is_consumed_verbatim():
    # The -D value must not be misread as command letters even if it looks like some.
    assert normalize_argv(["-D", "/path", "m"], COMMANDS) == ["-D", "/path", "-m"]


def test_unknown_token_left_untouched():
    # 'xyz' contains characters that aren't registered commands.
    assert normalize_argv(["xyz"], COMMANDS) == ["xyz"]


def test_already_flagged_passes_through():
    assert normalize_argv(["-u"], COMMANDS) == ["-u"]


def test_empty_argv():
    assert normalize_argv([], COMMANDS) == []


def test_trailing_d_without_value():
    assert normalize_argv(["-D"], COMMANDS) == ["-D"]
