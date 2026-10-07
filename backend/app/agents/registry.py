"""Who is on the team. Used by the API, the frontend graph and the trace header."""

from dataclasses import asdict, dataclass

from app.config import AGENT_IDS, Settings


@dataclass(frozen=True)
class AgentSpec:
    id: str
    name: str
    kind: str
    role: str
    tools: tuple[str, ...] = ()


AGENT_SPECS: dict[str, AgentSpec] = {
    "coordinator": AgentSpec(
        id="coordinator",
        name="Coordinator",
        kind="orchestrator",
        role="Breaks the query into a research plan, decides which agent acts next, "
             "re-plans when tasks fail or the critic finds gaps, and decides when the report is done.",
    ),
    "hn_scout": AgentSpec(
        id="hn_scout",
        name="HN Scout",
        kind="researcher",
        role="Finds Hacker News stories and reads their comment threads for practitioner sentiment.",
        tools=("search_hackernews", "get_front_page", "get_story_comments"),
    ),
    "web_researcher": AgentSpec(
        id="web_researcher",
        name="Web Researcher",
        kind="researcher",
        role="Searches the web and news for facts, official sources and recent developments.",
        tools=("web_search", "news_search"),
    ),
    "article_reader": AgentSpec(
        id="article_reader",
        name="Article Reader",
        kind="researcher",
        role="Reads the full text of the most important sources and extracts facts and figures.",
        tools=("read_article",),
    ),
    "writer": AgentSpec(
        id="writer",
        name="Writer",
        kind="synthesis",
        role="Drafts the cited report from the evidence store and revises it against the critic's "
             "issues, disputing the ones it disagrees with.",
    ),
    "critic": AgentSpec(
        id="critic",
        name="Critic",
        kind="review",
        role="Fact-checks each draft against the evidence and an automated citation check, rules "
             "on the writer's disputes, and sends revision requests or research gaps back.",
    ),
}

assert tuple(AGENT_SPECS) == AGENT_IDS


def describe_agents(settings: Settings) -> list[dict]:
    return [{**asdict(spec), "model": settings.model_for(spec.id)} for spec in AGENT_SPECS.values()]
