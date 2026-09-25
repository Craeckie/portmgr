import textwrap

import pytest

from portmgr import envmove


def dedent(text):
    return textwrap.dedent(text).lstrip("\n")


def by_key(entries):
    return {e.key: e for e in entries}


# --- collect_env ------------------------------------------------------------

def test_collects_dict_and_list_form():
    entries = by_key(envmove.collect_env(dedent("""
        services:
          web:
            environment:
              DB_PASSWORD: hunter2
              "QUOTED": 'single quoted'
          worker:
            environment:
              - API_TOKEN=abc123
              - "SPACED=with space"
    """)))
    assert entries["DB_PASSWORD"].value == "hunter2"
    assert entries["DB_PASSWORD"].services == ["web"]
    assert entries["DB_PASSWORD"].form == "dict"
    assert entries["QUOTED"].value == "single quoted"
    assert entries["API_TOKEN"].value == "abc123"
    assert entries["API_TOKEN"].form == "list"
    assert entries["SPACED"].value == "with space"
    assert all(e.skip is None for e in entries.values())


def test_dollar_escape_becomes_literal_dollar():
    entries = by_key(envmove.collect_env(dedent("""
        services:
          web:
            environment:
              A: pa$$word
          worker:
            environment:
              - B=x$$y
    """)))
    assert entries["A"].value == "pa$word"
    assert entries["B"].value == "x$y"


@pytest.mark.parametrize("line, quiet", [
    ("A: ${A}", True),
    ("A: \"${A}\"", True),
    ("A: $A", True),
    ("A: postgres://u:${PW}@db/app", False),
    ("A: pa$$$X", False),
    ("A:", True),
    ("A: ~", True),
])
def test_interpolated_and_empty_values_are_skipped(line, quiet):
    entries = envmove.collect_env(dedent(f"""
        services:
          web:
            environment:
              {line}
    """))
    assert len(entries) == 1
    assert entries[0].skip is not None
    assert entries[0].quiet is quiet


def test_list_pass_through_and_interpolated_are_skipped():
    entries = by_key(envmove.collect_env(dedent("""
        services:
          web:
            environment:
              - HOST_VAR
              - REF=${REF}
              - EMPTY=
              - =nameless
    """)))
    assert all(e.skip for e in entries.values())


@pytest.mark.parametrize("raw, ok", [
    ("5432", True),
    ("-12", True),
    ("true", True),
    ("false", True),
    ("0.5", True),
    ("yes", True),       # YAML 1.2 (compose) keeps it a string
    ("1.2.3", True),
    ("12:30", True),
    ("True", False),     # compose renders it as "true"
    ("FALSE", False),
    ("007", False),      # -> "7"
    ("0o17", False),     # -> "15"
    ("0x1F", False),
    ("1_000", False),
    ("1.50", False),     # -> "1.5"
    ("1e3", False),
    (".inf", False),
    ("+5", False),
    ("-0", False),
])
def test_plain_scalars_compose_would_rewrite_are_skipped(raw, ok):
    entries = envmove.collect_env(dedent(f"""
        services:
          web:
            environment:
              A: {raw}
    """))
    assert (entries[0].skip is None) is ok, entries[0].skip
    if ok:
        assert entries[0].value == raw


def test_quoted_number_is_moved_verbatim():
    entries = envmove.collect_env(dedent("""
        services:
          web:
            environment:
              A: '007'
    """))
    assert entries[0].skip is None
    assert entries[0].value == "007"


def test_block_scalars_anchors_and_tags_are_skipped():
    entries = by_key(envmove.collect_env(dedent("""
        services:
          web:
            environment:
              BLOCK: |
                line one
                line two
              ANCHORED: &pw secret
              ALIASED: *pw
              TAGGED: !!str 5432
              NEWLINE: "a\\nb"
    """)))
    for key in ("BLOCK", "ANCHORED", "ALIASED", "TAGGED", "NEWLINE"):
        assert entries[key].skip, key


@pytest.mark.parametrize("value", ["ends\\\\", "has\\\\'quote"])
def test_values_dotenv_cannot_represent_are_skipped(value):
    entries = envmove.collect_env(dedent(f"""
        services:
          web:
            environment:
              A: "{value}"
    """))
    assert entries[0].skip


def test_shared_environment_block_is_listed_once():
    entries = envmove.collect_env(dedent("""
        x-env: &env
          SECRET_KEY: abc
        services:
          api:
            environment: *env
          worker:
            environment: *env
    """))
    assert len(entries) == 1
    assert entries[0].services == ["api", "worker"]


def test_secret_flag_follows_secret_key_pattern():
    entries = by_key(envmove.collect_env(dedent("""
        services:
          web:
            environment:
              DB_PASSWORD: x
              TZ: Europe/Berlin
    """)))
    assert entries["DB_PASSWORD"].secret
    assert not entries["TZ"].secret


def test_no_services_or_invalid_yaml():
    assert envmove.collect_env("version: '3'\n") == []
    with pytest.raises(envmove.yaml.YAMLError):
        envmove.collect_env("services: [\n")


# --- dotenv -----------------------------------------------------------------

@pytest.mark.parametrize("value, expected", [
    ("plain-value_1./:@+", "plain-value_1./:@+"),
    ("with space", "'with space'"),
    ("pa$word", "'pa$word'"),
    ("hash # x", "'hash # x'"),
    ("it's", "'it\\'s'"),
    ('dq"', "'dq\"'"),
    ("back\\slash", "'back\\slash'"),
])
def test_dotenv_format(value, expected):
    assert envmove.dotenv_format(value) == expected


def test_parse_dotenv_round_trips_format():
    values = ["plain", "with space", "pa$word", "it's", "back\\slash", 'dq"']
    text = "".join(f"K{i}={envmove.dotenv_format(v)}\n" for i, v in enumerate(values))
    parsed = envmove.parse_dotenv(text)
    assert parsed == {f"K{i}": v for i, v in enumerate(values)}


def test_parse_dotenv_marks_unsure_values_unknown():
    parsed = envmove.parse_dotenv(dedent("""
        # comment
        export A=plain
        B=with $REF
        C="double quoted"
        D=value # trailing comment
        E="double $REF"
        F='unterminated
    """))
    assert parsed["A"] == "plain"
    assert parsed["B"] is None
    assert parsed["C"] == "double quoted"
    assert parsed["D"] == "value"
    assert parsed["E"] is None
    assert parsed["F"] is None


# --- plan_moves / apply ------------------------------------------------------

COMPOSE = dedent("""
    # stack comment
    services:
      db:
        image: postgres
        environment:
          POSTGRES_PASSWORD: hunter2   # keep this comment
          TZ: Europe/Berlin
      app:
        environment:
          - POSTGRES_PASSWORD=hunter2
          - "SECRET_KEY=s3cr3t value"
          - DEBUG=true
      other:
        environment:
          POSTGRES_PASSWORD: different
""")


def select(entries, *specs):
    return [e for e in entries if (e.services[0], e.key) in specs]


def test_plan_shares_equal_values_and_prefixes_conflicts():
    entries = envmove.collect_env(COMPOSE)
    chosen = select(entries, ("db", "POSTGRES_PASSWORD"), ("app", "POSTGRES_PASSWORD"),
                    ("other", "POSTGRES_PASSWORD"), ("app", "SECRET_KEY"))
    moves = envmove.plan_moves(chosen, {}, COMPOSE, reserved=set())
    names = {(m.entry.services[0], m.entry.key): (m.name, m.append) for m in moves}
    assert names[("db", "POSTGRES_PASSWORD")] == ("POSTGRES_PASSWORD", True)
    assert names[("app", "POSTGRES_PASSWORD")] == ("POSTGRES_PASSWORD", False)
    assert names[("other", "POSTGRES_PASSWORD")] == ("OTHER_POSTGRES_PASSWORD", True)
    assert names[("app", "SECRET_KEY")] == ("SECRET_KEY", True)


def test_plan_reuses_equal_dotenv_value_and_avoids_different_one():
    entries = envmove.collect_env(COMPOSE)
    chosen = select(entries, ("db", "POSTGRES_PASSWORD"), ("db", "TZ"))
    moves = envmove.plan_moves(chosen, {"POSTGRES_PASSWORD": "hunter2", "TZ": "UTC"},
                               COMPOSE, reserved=set())
    names = {m.entry.key: (m.name, m.append) for m in moves}
    assert names["POSTGRES_PASSWORD"] == ("POSTGRES_PASSWORD", False)
    assert names["TZ"] == ("DB_TZ", True)


def test_plan_avoids_reserved_and_already_referenced_names():
    text = COMPOSE + "  extra:\n    command: echo ${TZ}\n"
    entries = envmove.collect_env(text)
    chosen = select(entries, ("db", "TZ"), ("app", "DEBUG"))
    moves = envmove.plan_moves(chosen, {}, text, reserved={"DEBUG"})
    names = {m.entry.key: m.name for m in moves}
    assert names == {"TZ": "DB_TZ", "DEBUG": "APP_DEBUG"}


def test_apply_compose_only_touches_moved_values():
    entries = envmove.collect_env(COMPOSE)
    chosen = select(entries, ("db", "POSTGRES_PASSWORD"), ("app", "SECRET_KEY"))
    moves = envmove.plan_moves(chosen, {}, COMPOSE, reserved=set())
    result = envmove.apply_compose(COMPOSE, moves)
    expected = (COMPOSE
                .replace("POSTGRES_PASSWORD: hunter2   #", 'POSTGRES_PASSWORD: "${POSTGRES_PASSWORD}"   #')
                .replace('- "SECRET_KEY=s3cr3t value"', '- "SECRET_KEY=${SECRET_KEY}"'))
    assert result == expected
    # And the result still parses to the references.
    moved = by_key(envmove.collect_env(result))
    assert moved["SECRET_KEY"].skip and moved["SECRET_KEY"].quiet


def test_apply_compose_in_flow_mapping_stays_valid_yaml():
    text = "services:\n  web:\n    environment: {A: secret, B: keep}\n"
    moves = envmove.plan_moves(select(envmove.collect_env(text), ("web", "A")), {}, text, set())
    result = envmove.apply_compose(text, moves)
    assert result == 'services:\n  web:\n    environment: {A: "${A}", B: keep}\n'
    assert envmove.yaml.safe_load(result)["services"]["web"]["environment"]["A"] == "${A}"


def test_dotenv_append_text():
    assert envmove.dotenv_append_text("", [("A", "x y")]) == "A='x y'\n"
    assert envmove.dotenv_append_text("OLD=1", [("A", "b")]) == "OLD=1\nA=b\n"
    assert envmove.dotenv_append_text("OLD=1\n", [("A", "b")]) == "OLD=1\nA=b\n"


# --- parse_selection ----------------------------------------------------------

@pytest.mark.parametrize("answer, expected", [
    ("", {0, 2}),
    ("a", {0, 1, 2, 3}),
    ("n", set()),
    ("1,3", {0, 2}),
    ("2-4", {1, 2, 3}),
    (" 1 4 ", {0, 3}),
])
def test_parse_selection(answer, expected):
    assert envmove.parse_selection(answer, 4, {0, 2}) == expected


@pytest.mark.parametrize("answer", ["5", "0", "x", "3-1"])
def test_parse_selection_rejects_bad_input(answer):
    with pytest.raises(ValueError):
        envmove.parse_selection(answer, 4, set())
