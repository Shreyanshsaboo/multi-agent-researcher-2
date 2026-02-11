# 🤖 Multi-Agent AI Researcher

[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.28+-FF4B4B.svg)](https://streamlit.io/)
[![OpenAI](https://img.shields.io/badge/OpenAI-GPT--4o-412991.svg)](https://openai.com/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

An intelligent multi-agent system that leverages GPT-4o to autonomously research, analyze, and synthesize information from HackerNews and the web. Built with modern AI orchestration frameworks and designed for scalable, collaborative agent workflows.

## 🎯 Overview

This project demonstrates advanced AI agent orchestration by implementing a coordinated team of specialized agents that work together to conduct comprehensive research. The system showcases practical applications of Large Language Models (LLMs) in automated content research and generation.

**Key Highlights:**
- Multi-agent architecture with role-based specialization
- Real-time web scraping and content extraction
- Intelligent workflow orchestration and task delegation
- Production-ready Streamlit interface

## ✨ Features

- **🔍 Autonomous Research**: Automatically discovers and analyzes trending HackerNews stories
- **🤝 Collaborative Agents**: Three specialized AI agents work in concert to gather and synthesize information
- **🌐 Web Intelligence**: Integrates DuckDuckGo search and article extraction for comprehensive coverage
- **📊 Structured Outputs**: Generates well-formatted reports with citations and references
- **⚡ Real-Time Processing**: Stream-capable architecture for responsive user experience

## 🏗️ Architecture

The system employs a hierarchical multi-agent architecture:

```
┌─────────────────────────────────────┐
│      HackerNews Team (Orchestrator)  │
└──────────────┬──────────────────────┘
               │
       ┌───────┴────────┬────────────────┐
       │                │                 │
┌──────▼──────┐  ┌─────▼──────┐  ┌──────▼──────┐
│ HackerNews  │  │    Web     │  │   Article   │
│ Researcher  │  │  Searcher  │  │   Reader    │
└─────────────┘  └────────────┘  └─────────────┘
```

### Agent Roles

| Agent | Responsibility | Technology |
|-------|---------------|------------|
| **HackerNews Researcher** | Fetches top stories and trending content | HackerNews API |
| **Web Searcher** | Discovers additional context and related information | DuckDuckGo API |
| **Article Reader** | Extracts and parses full article content | Newspaper4k |
| **Team Orchestrator** | Coordinates agent workflows and synthesizes findings | GPT-4o |

## 🚀 Quick Start

### Prerequisites

- Python 3.8 or higher
- OpenAI API key ([Get one here](https://platform.openai.com/))

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/Shreyanshsaboo/multi-agent-researcher.git
   cd multi-agent-researcher
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Launch the application**
   ```bash
   streamlit run research_agent.py
   ```

4. **Enter your OpenAI API key** in the application interface

5. **Start researching!** Enter any query related to HackerNews content or tech trends

## 💡 Usage Examples

**Sample Queries:**
- "Summarize the top AI and machine learning stories from HackerNews today"
- "Find recent discussions about large language models"
- "Research trending startups mentioned on HackerNews this week"
- "Analyze the most popular programming language discussions"

## 🛠️ Technical Stack

- **Framework**: [Streamlit](https://streamlit.io/) - Interactive web application framework
- **LLM**: [OpenAI GPT-4o-mini](https://openai.com/) - Language model for agent intelligence
- **Agent Framework**: [Agno](https://github.com/agno-agi/agno) - Multi-agent orchestration
- **APIs & Tools**:
  - HackerNews API - Story and user data
  - DuckDuckGo Search - Web search capabilities
  - Newspaper4k - Article extraction and parsing

## 📋 System Workflow

1. **Query Reception**: User submits research query through Streamlit interface
2. **Story Discovery**: HackerNews Researcher fetches relevant stories
3. **Content Extraction**: Article Reader processes URLs and extracts full content
4. **Context Enhancement**: Web Searcher gathers supplementary information
5. **Synthesis**: Team Orchestrator compiles comprehensive report with citations
6. **Output**: Structured markdown report delivered to user

## 🔧 Configuration

The system uses GPT-4o-mini for cost-effective operations. To use different models:

```python
model=OpenAIChat(id="gpt-4o")  # For enhanced performance
```

## 🌟 Key Learnings & Skills Demonstrated

- **AI/ML Engineering**: Multi-agent system design and implementation
- **Software Architecture**: Modular, scalable agent-based architecture
- **API Integration**: Seamless integration of multiple external APIs
- **Python Development**: Clean, maintainable code following best practices
- **UI/UX Design**: User-friendly interface with Streamlit
- **Prompt Engineering**: Effective agent instruction design for optimal outputs

## 🔮 Future Enhancements

- [ ] Add support for multiple LLM providers (Anthropic, Google, etc.)
- [ ] Implement caching layer for improved performance
- [ ] Add export functionality (PDF, JSON, Markdown)
- [ ] Integrate vector database for semantic search
- [ ] Deploy as containerized application (Docker)
- [ ] Add user authentication and session management

## 📝 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🤝 Contributing

Contributions, issues, and feature requests are welcome! Feel free to check the issues page.

## 👨‍💻 Author

**Shreyansh Saboo**

- GitHub: [@Shreyanshsaboo](https://github.com/Shreyanshsaboo)

## 🙏 Acknowledgments

- OpenAI for GPT-4o API
- Streamlit for the amazing framework
- HackerNews for the API access
- The open-source community

---

⭐ **If you find this project useful, please consider giving it a star!**

