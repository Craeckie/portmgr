import json


from portmgr import wrapper


class FakeCompleted:
    def __init__(self, returncode=0):
        self.returncode = returncode


def test_run_compose_passes_through_returncode(monkeypatch):
    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        return FakeCompleted(returncode=7)

    monkeypatch.delenv("PORTMGR_IN_SCRIPT", raising=False)
    monkeypatch.setattr(wrapper, "run", fake_run)

    rc = wrapper.runCompose(["up", "-d"])
    assert rc == 7
    assert captured["command"] == ["docker", "compose", "up", "-d"]


def test_run_compose_in_script_adds_ansi_never(monkeypatch):
    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        return FakeCompleted(returncode=0)

    monkeypatch.setenv("PORTMGR_IN_SCRIPT", "true")
    monkeypatch.setattr(wrapper, "run", fake_run)

    wrapper.runCompose(["ps"])
    assert captured["command"] == ["docker", "compose", "--ansi", "never", "ps"]


def test_run_compose_in_script_case_insensitive(monkeypatch):
    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        return FakeCompleted(0)

    monkeypatch.setenv("PORTMGR_IN_SCRIPT", "TRUE")
    monkeypatch.setattr(wrapper, "run", fake_run)

    wrapper.runCompose(["ps"])
    assert "--ansi" in captured["command"]


def test_run_buildx_builds_command(monkeypatch):
    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        return FakeCompleted(3)

    monkeypatch.setattr(wrapper, "run", fake_run)

    rc = wrapper.runBuildx(["bake", "svc"])
    assert rc == 3
    assert captured["command"] == ["docker", "buildx", "bake", "svc"]


def test_get_services_running_multiline(monkeypatch):
    payload = "\n".join([
        json.dumps({"Name": "web-1"}),
        json.dumps({"Name": "db-1"}),
    ]).encode()
    monkeypatch.setattr(wrapper, "check_output", lambda *a, **kw: payload)

    assert wrapper.getServicesRunning() == ["web-1", "db-1"]


def test_get_services_running_single_object(monkeypatch):
    payload = json.dumps({"Name": "solo-1"}).encode()
    monkeypatch.setattr(wrapper, "check_output", lambda *a, **kw: payload)

    assert wrapper.getServicesRunning() == ["solo-1"]
