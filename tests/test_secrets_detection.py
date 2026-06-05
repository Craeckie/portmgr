import textwrap

from portmgr import secrets


def write_compose(tmp_path, content):
    path = tmp_path / "docker-compose.yml"
    path.write_text(textwrap.dedent(content))
    return str(path)


def test_dict_environment_literal_secret(tmp_path):
    path = write_compose(tmp_path, """
        services:
          web:
            environment:
              DB_PASSWORD: hunter2
    """)
    assert secrets.find_secret_keys(path) == [("web", "DB_PASSWORD")]


def test_list_environment_key_value(tmp_path):
    path = write_compose(tmp_path, """
        services:
          web:
            environment:
              - API_TOKEN=abc123
    """)
    assert secrets.find_secret_keys(path) == [("web", "API_TOKEN")]


def test_list_entry_without_equals_is_ignored(tmp_path):
    # `SECRET_KEY` with no value (pass-through from host env) carries no literal.
    path = write_compose(tmp_path, """
        services:
          web:
            environment:
              - SECRET_KEY
    """)
    assert secrets.find_secret_keys(path) == []


def test_empty_value_not_flagged(tmp_path):
    path = write_compose(tmp_path, """
        services:
          web:
            environment:
              PASSWORD: ""
    """)
    assert secrets.find_secret_keys(path) == []


def test_variable_reference_values_excluded(tmp_path):
    path = write_compose(tmp_path, """
        services:
          web:
            environment:
              DB_PASSWORD: ${DB_PASSWORD}
              API_KEY: $API_KEY
    """)
    assert secrets.find_secret_keys(path) == []


def test_key_pattern_coverage(tmp_path):
    path = write_compose(tmp_path, """
        services:
          svc:
            environment:
              MY_PASSWORD: a
              MY_PASS: b
              APP_SECRET: c
              AUTH_TOKEN: d
              ENCRYPTION_KEY: e
              APIKEY: f
              DB_CREDENTIAL: g
              LANG: en_US.UTF-8
    """)
    found_keys = {k for _, k in secrets.find_secret_keys(path)}
    assert found_keys == {
        "MY_PASSWORD", "MY_PASS", "APP_SECRET",
        "AUTH_TOKEN", "ENCRYPTION_KEY", "APIKEY", "DB_CREDENTIAL",
    }
    assert "LANG" not in found_keys


def test_case_insensitive_key_match(tmp_path):
    path = write_compose(tmp_path, """
        services:
          svc:
            environment:
              db_password: secret
    """)
    assert secrets.find_secret_keys(path) == [("svc", "db_password")]


def test_missing_file_returns_empty(tmp_path):
    assert secrets.find_secret_keys(str(tmp_path / "nope.yml")) == []


def test_malformed_yaml_returns_empty(tmp_path):
    path = tmp_path / "docker-compose.yml"
    path.write_text("services: [unclosed\n  : :")
    assert secrets.find_secret_keys(str(path)) == []


def test_non_dict_document_returns_empty(tmp_path):
    path = tmp_path / "docker-compose.yml"
    path.write_text("- just\n- a\n- list\n")
    assert secrets.find_secret_keys(str(path)) == []


def test_non_dict_service_is_skipped(tmp_path):
    path = write_compose(tmp_path, """
        services:
          broken: "not-a-mapping"
          web:
            environment:
              TOKEN: t
    """)
    assert secrets.find_secret_keys(path) == [("web", "TOKEN")]


def test_environment_absent_is_skipped(tmp_path):
    path = write_compose(tmp_path, """
        services:
          web:
            image: nginx
    """)
    assert secrets.find_secret_keys(path) == []
