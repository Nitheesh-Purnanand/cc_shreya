import os

os.environ["SKIP_MODEL_LOAD"] = "1"
os.environ["MODEL_VERSION"] = "v-test"
os.environ["POD_NAME"] = "pod-test"

import app as service
import pytest
from fastapi.testclient import TestClient

GOOD = '{"intent": "weather_query", "date": null, "time": null, "place": "london"}'


@pytest.fixture
def client(monkeypatch):
    service.state.update(model=None, tok=None)
    monkeypatch.delenv("FAULT_INJECT", raising=False)
    with TestClient(service.app) as c:
        yield c


def ready(monkeypatch, output):
    service.state.update(model=object(), tok=object())
    monkeypatch.setattr(service.inference, "generate", lambda *a: output)


def test_health_and_readiness(client, monkeypatch):
    assert client.get("/healthz").status_code == 200
    assert client.get("/readyz").status_code == 503
    ready(monkeypatch, GOOD)
    assert client.get("/readyz").status_code == 200


def test_parse_ok_with_headers(client, monkeypatch):
    ready(monkeypatch, GOOD)
    r = client.post("/parse", json={"text": "what is the weather in london"})
    assert r.status_code == 200
    assert r.json() == {"intent": "weather_query", "date": None, "time": None, "place": "london"}
    assert r.headers["X-Model-Version"] == "v-test" and r.headers["X-Served-By"] == "pod-test"


@pytest.mark.parametrize("output", ['{"intent": "weather_query"', '{"intent": "nope", "date": null, "time": null, "place": null}'])
def test_invalid_model_output_is_500(client, monkeypatch, output):
    ready(monkeypatch, output)
    r = client.post("/parse", json={"text": "x"})
    assert r.status_code == 500 and r.json() == {"error": "invalid_model_output"}


def test_fault_inject(client, monkeypatch):
    ready(monkeypatch, GOOD)
    monkeypatch.setenv("FAULT_INJECT", "1")
    r = client.post("/parse", json={"text": "what is the weather in london"})
    assert r.status_code == 500 and r.json() == {"error": "invalid_model_output"}
