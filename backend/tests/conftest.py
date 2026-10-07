import httpx
import pytest

from app.events import RunChannel
from app.evidence import EvidenceStore
from app.tools import ToolContext

ALGOLIA_SEARCH = {
    "hits": [
        {
            "objectID": "101",
            "title": "Inference prices fell 80% this year",
            "url": "https://blog.example.com/prices",
            "points": 412,
            "num_comments": 230,
            "created_at": "2026-09-30T10:00:00Z",
            "author": "pg",
        },
        {
            "objectID": "102",
            "title": "Ask HN: How do you budget for LLM APIs?",
            "url": None,
            "points": 88,
            "num_comments": 61,
            "created_at": "2026-09-28T08:00:00Z",
            "author": "dang",
        },
    ]
}

ALGOLIA_ITEM = {
    "id": 101,
    "title": "Inference prices fell 80% this year",
    "url": "https://blog.example.com/prices",
    "created_at": "2026-09-30T10:00:00Z",
    "text": None,
    "children": [
        {"author": "a", "text": "<p>Short take</p>", "children": []},
        {"author": "b", "text": "Prices fell but <i>latency</i> got worse", "children": [{}, {}, {}]},
        {"author": "c", "text": None, "children": []},
    ],
}


def algolia_handler(request: httpx.Request) -> httpx.Response:
    if request.url.path.startswith("/api/v1/items/"):
        return httpx.Response(200, json=ALGOLIA_ITEM)
    if request.url.params.get("query") == "nothing matches":
        return httpx.Response(200, json={"hits": []})
    return httpx.Response(200, json=ALGOLIA_SEARCH)


@pytest.fixture
def channel():
    return RunChannel("test-run")


@pytest.fixture
def evidence():
    return EvidenceStore()


@pytest.fixture
async def http():
    async with httpx.AsyncClient(transport=httpx.MockTransport(algolia_handler)) as client:
        yield client


@pytest.fixture
def make_ctx(channel, evidence, http):
    def factory(agent_id="hn_scout", **kwargs):
        return ToolContext(channel=channel, agent_id=agent_id, task_id="t1",
                           evidence=evidence, http=http, **kwargs)
    return factory
