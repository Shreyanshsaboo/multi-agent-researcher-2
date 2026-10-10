"""Multi-Agent AI Researcher, backed by the Groq API.

A Streamlit front end over an Agno team. An orchestrator delegates story
discovery, article extraction, and web enrichment to three single-tool agents,
then merges their output into one cited report.
"""

import os
from pathlib import Path

import streamlit as st
from agno.agent import Agent
from agno.models.groq import Groq
from agno.run.agent import RunOutput
from agno.team import Team
from agno.tools.hackernews import HackerNewsTools
from agno.tools.newspaper4k import Newspaper4kTools
from agno.tools.websearch import WebSearchTools
from dotenv import load_dotenv

# The .env file lives in the repository root, one level up.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

MODEL_ID = "openai/gpt-oss-120b"

# Groq's free tier caps every model at 8,000 tokens per minute, and rejects any
# single request over that outright. Groq counts the reserved completion budget
# toward the request, so these limits keep each call well under the cap.
MAX_TOKENS = 2048
ARTICLE_CHARS = 4000  # roughly 1,000 tokens per article read
SEARCH_RESULTS = 5
# Caps tool calls per member run. Without it, a member that hits an unreadable
# page or an empty search keeps retrying variations and burns the token budget.
TOOL_CALL_LIMIT = 5


def groq_model() -> Groq:
    """A Groq model that waits out per-minute rate limits instead of failing.

    Backoff runs 10s, 20s, 40s, which spans a full one-minute TPM window.
    """
    return Groq(
        id=MODEL_ID,
        max_tokens=MAX_TOKENS,
        retries=3,
        delay_between_retries=10,
        exponential_backoff=True,
    )

# The workflow definition. Reordering these lines reorders the pipeline, which
# is the fastest way to try a different research strategy.
TEAM_INSTRUCTIONS = [
    "First, search hackernews for what the user is asking about.",
    "Then, ask the article reader to read the links for the stories to get more information.",
    "Important: you must provide the article reader with the links to read.",
    "Then, ask the web searcher to search for each story to get more information.",
    "Finally, provide a thoughtful and engaging summary.",
]


def build_team() -> Team:
    """Assemble the orchestrator and its member agents.

    Every member holds exactly one tool. With a single option per step there is
    no tool selection to get wrong, and the routing decision moves up to the
    orchestrator instead.
    """
    hn_researcher = Agent(
        name="HackerNews Researcher",
        model=groq_model(),
        role="Gets top stories from hackernews.",
        tools=[HackerNewsTools()],
    )

    article_reader = Agent(
        name="Article Reader",
        model=groq_model(),
        role="Reads articles from URLs.",
        tools=[Newspaper4kTools(article_length=ARTICLE_CHARS)],
        instructions=[
            "Only read the URLs you were given.",
            "If a URL cannot be read, skip it. Never guess or construct other URLs.",
        ],
        tool_call_limit=TOOL_CALL_LIMIT,
    )

    web_searcher = Agent(
        name="Web Searcher",
        model=groq_model(),
        role="Searches the web for information on a topic",
        # "auto" rotates across free, keyless engines (Bing, Yahoo, DuckDuckGo, ...)
        # and falls back when one returns nothing, instead of pinning to a
        # single engine that rate-limits rapid queries.
        tools=[WebSearchTools(backend="auto", fixed_max_results=SEARCH_RESULTS)],
        tool_call_limit=TOOL_CALL_LIMIT,
        # Models have no reliable sense of the current date, so recency-sensitive
        # queries would otherwise resolve against the training cutoff.
        add_datetime_to_context=True,
    )

    return Team(
        name="HackerNews Team",
        model=groq_model(),
        members=[hn_researcher, web_searcher, article_reader],
        instructions=TEAM_INSTRUCTIONS,
        markdown=True,
        # Surfaces each member's intermediate output. Useful while tracing a
        # delegation path; turn both off for a clean end-user report.
        debug_mode=True,
        show_members_responses=True,
    )


st.title("Multi-Agent AI Researcher")
st.caption(
    "Research a topic on HackerNews with a team of specialized agents: story "
    "discovery, full-text extraction, and web enrichment, merged into one report."
)

# A key in .env skips the prompt; otherwise fall back to asking in the UI.
groq_api_key = os.getenv("GROQ_API_KEY") or st.text_input(
    "Groq API Key", type="password"
)

if groq_api_key:
    os.environ["GROQ_API_KEY"] = groq_api_key
    hackernews_team = build_team()

    query = st.text_input("Enter your report query")
    if query:
        response: RunOutput = hackernews_team.run(query, stream=False)
        st.write(response.content)
