"""Multi-Agent AI Researcher, backed by the OpenAI API.

A Streamlit front end over an Agno team. An orchestrator delegates story
discovery, article extraction, and web enrichment to three single-tool agents,
then merges their output into one cited report.
"""

import os

import streamlit as st
from agno.agent import Agent
from agno.models.openai import OpenAIChat
from agno.run.agent import RunOutput
from agno.team import Team
from agno.tools.duckduckgo import DuckDuckGoTools
from agno.tools.hackernews import HackerNewsTools
from agno.tools.newspaper4k import Newspaper4kTools

MODEL_ID = "gpt-4o-mini"

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
        model=OpenAIChat(id=MODEL_ID),
        role="Gets top stories from hackernews.",
        tools=[HackerNewsTools()],
    )

    article_reader = Agent(
        name="Article Reader",
        model=OpenAIChat(id=MODEL_ID),
        role="Reads articles from URLs.",
        tools=[Newspaper4kTools()],
    )

    web_searcher = Agent(
        name="Web Searcher",
        model=OpenAIChat(id=MODEL_ID),
        role="Searches the web for information on a topic",
        tools=[DuckDuckGoTools()],
        # Models have no reliable sense of the current date, so recency-sensitive
        # queries would otherwise resolve against the training cutoff.
        add_datetime_to_context=True,
    )

    return Team(
        name="HackerNews Team",
        model=OpenAIChat(id=MODEL_ID),
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

openai_api_key = st.text_input("OpenAI API Key", type="password")

if openai_api_key:
    os.environ["OPENAI_API_KEY"] = openai_api_key
    hackernews_team = build_team()

    query = st.text_input("Enter your report query")
    if query:
        response: RunOutput = hackernews_team.run(query, stream=False)
        st.write(response.content)
