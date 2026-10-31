<div align="center">
  <h1>✈️ TravelBrain</h1>
  <h3>Your AI-powered multi-agent travel planning assistant</h3>

Plan smarter trips with AI-powered research, personalized budgets, and
optimized day-wise itineraries.

![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-Backend-009688?logo=fastapi&logoColor=white)
![LangGraph](https://img.shields.io/badge/LangGraph-Agent%20Orchestration-1C3C3C)
</div>

------------------------------------------------------------------------

## 📌 Overview

TravelBrain is an AI-powered travel planning application that helps
users research and organize trips through a conversational interface.
Instead of switching between multiple websites and manually coordinating
travel details, users can describe their requirements in natural
language and receive a consolidated travel plan.

The application uses a **multi-agent architecture** orchestrated with
LangGraph. Specialized agents handle different parts of the planning
process, including flights, accommodation, weather, and itinerary
research. Their outputs are combined into a final response that users
can review and refine.

TravelBrain also includes two dedicated planning and optimization
modules:

-   **Smart Budget Analyzer** -- evaluates trip expenses against a
    selected travel style and budget.
-   **A\* Route Optimizer** -- creates feasible day-wise attraction
    sequences while considering travel time, opening hours, visit
    durations, and return to the hotel.

## ✨ Key Features

### 🤖 Multi-Agent AI Travel Planning

-   Accepts trip requests in natural language.
-   Uses specialized agents for flight, hotel, weather, and itinerary
    research.
-   Combines agent outputs into a consolidated travel plan.
-   Supports follow-up questions within a saved trip session.

### 💰 Smart Budget Analyzer

-   Breaks down estimated expenses into categories such as travel,
    accommodation, food, local transport, activities, and miscellaneous
    costs.
-   Supports six travel profiles: **Balanced, Luxury, Adventure,
    Culture, Food, and Family**.
-   Uses profile-based category weights to make budget recommendations
    more relevant to the traveler's preferences.
-   Keeps a contingency reserve in the budget analysis.
-   Treats the budget as a soft constraint: when estimates exceed the
    target, it explains the difference and possible trade-offs rather
    than silently changing user-entered costs.
-   Supports INR, USD, EUR, GBP, AED, and JPY as selected
    planning/display currencies.

> **Note:** Currency selection keeps planning estimates consistently
> labelled. It is not a live foreign-exchange converter, and changing
> the selected currency does not automatically convert amounts already
> entered.

### 🗺️ A\* Day-wise Route Optimization

-   Groups selected attractions by their specified area and plans each
    area as a separate day.
-   Starts and ends each day's route at the hotel.
-   Uses A\* search to find an efficient attraction order.
-   Enforces supplied attraction opening windows, visit durations, daily
    start/end times, and hotel return feasibility.
-   Accounts for configurable buffer time and a meal break.
-   Reports route distance, estimated travel time, visit time, and
    schedule details.
-   Explains infeasible plans and suggests adjustments instead of
    silently dropping selected attractions.

### 🍽️ Itinerary Options and Meal Discovery

-   Can prepare efficient, balanced, and relaxed itinerary options using
    the configured research and language-model integrations.
-   Includes nearby food-place information when available.
-   Presents route details in a user-friendly format rather than
    exposing raw optimizer data.

### 💾 Session and Application Support

-   Saves trip conversations using the configured PostgreSQL-backed
    LangGraph checkpointer.
-   Includes optional Redis caching for supported external data calls.
-   Provides a web interface for the main planner, budget analyzer, and
    route planner.

------------------------------------------------------------------------

## 🧠 How It Works

### 1. Multi-Agent Workflow

The main travel-planning workflow is built with **LangGraph**. The graph
coordinates specialized agents and passes the trip state through the
planning process.

``` mermaid
flowchart TD
    A([User Trip Request]) --> B[Flight Agent]
    B --> C[Hotel Agent]
    C --> D[Weather Agent]
    D --> E[Itinerary Agent]
    E --> F[Final Response Agent]
    F --> G([Consolidated Travel Plan])
```

Each agent focuses on a specific task. The final agent combines the
collected information into a response for the user.

### 2. Budget Analysis

The Budget Analyzer compares the user's available budget and expense
estimates with category allocations associated with the selected travel
profile.

The analysis follows this general approach:

1.  Read the total budget, expense estimates, travel profile, and trip
    context.
2.  Apply the selected profile's category weights.
3.  reserve a contingency amount.
4.  Compare estimated expenses with the recommended allocations.
5.  Explain overspending, remaining budget, and possible adjustments.

The analyzer is a deterministic, rule-based calculation module; it does
not train a machine-learning model.

### 3. A\* Route Optimization

The route optimizer uses **A\* search with an MST-based global
heuristic** to estimate the remaining travel cost.

The search state contains:

``` text
(last attraction, visited attractions, current time)
```

The heuristic estimates the remaining travel cost using:

\[ h(n) = d(`\text{current}`{=tex}, `\text{nearest unvisited}`{=tex}) +
MST(`\text{unvisited}`{=tex}) + d(`\text{unvisited}`{=tex},
`\text{hotel}`{=tex}) \]

Where:

-   `d(current, nearest unvisited)` estimates the connection from the
    current stop to an unvisited attraction.
-   `MST(unvisited)` estimates the minimum spanning tree cost connecting
    the remaining attractions.
-   `d(unvisited, hotel)` estimates a connection from the remaining
    attractions back to the hotel.

A\* combines the cost already travelled with this heuristic to
prioritize promising route states.

**Important implementation notes:** - The heuristic estimates travel
cost; scheduling constraints such as opening hours and visit durations
are checked during search expansion. - The MST-based lower-bound
interpretation depends on the travel-cost assumptions. Arbitrary
directional travel-time estimates may not satisfy the symmetry
assumptions used by a standard MST lower bound. - If pairwise
travel-time estimates are unavailable, the optimizer can fall back to
straight-line Haversine distance divided by a configurable average
speed. This is an approximation, not live road-routing data. - Opening
hours are only enforceable when valid opening and closing times are
provided. The optimizer does not independently verify attraction
hours. - The current area policy uses the attraction's supplied `area`
value. It does not automatically discover geographic clusters.

------------------------------------------------------------------------

## 🏗️ Technology Stack

  Layer                    Technologies
  ------------------------ -----------------------------------------------
  Backend                  Python 3.11+, FastAPI, Uvicorn
  Agent orchestration      LangGraph, LangChain
  Language model           Groq API (configurable model)
  External information     Tavily, AviationStack, OpenWeather
  Database / persistence   PostgreSQL, LangGraph Postgres Checkpointer
  Caching                  Redis (optional)
  Frontend                 HTML, CSS, JavaScript, Jinja2
  Optimization             A\* search, MST heuristic, Haversine distance
  Testing                  Python `unittest`

------------------------------------------------------------------------

## 📂 Project Structure

``` text
TravelBrain/
│
├── app.py
├── pyproject.toml
├── uv.lock
├── .env.example
├── Dockerfile
├── docker-compose.yml
├── vercel.json
│
├── src/
│   ├── agents/
│   │   ├── destination.py
│   │   ├── final_agent.py
│   │   ├── flight_agent.py
│   │   ├── hotel_agent.py
│   │   ├── itinerary_agent.py
│   │   ├── prompts.py
│   │   └── weather_agent.py
│   │
│   ├── api/
│   ├── clients/
│   ├── config/
│   ├── graph/
│   │   ├── graph.py
│   │   ├── runner.py
│   │   └── state.py
│   │
│   ├── mcp_servers/
│   ├── utils/
│   ├── budget_analyzer.py
│   └── route_optimizer.py
│
├── frontend/
│   ├── templates/
│   │   ├── index.html
│   │   ├── budget.html
│   │   └── route_planner.html
│   └── static/
│       ├── css/
│       └── js/
│
└── tests/
    ├── test_budget_analyzer.py
    └── test_route_optimizer.py
```

------------------------------------------------------------------------

## ⚙️ Getting Started

### Prerequisites

Before running TravelBrain locally, make sure you have:

-   Python **3.11 or later**
-   [uv](https://docs.astral.sh/uv/) for Python dependency management
-   A PostgreSQL database
-   API credentials for the integrations you intend to use

### 1. Clone the repository

Replace the URL below with your repository URL after pushing the project
to GitHub.

``` bash
git clone https://github.com/<YOUR_USERNAME>/<YOUR_REPOSITORY>.git
cd TravelBrain
```

### 2. Install dependencies

``` bash
uv sync
```

### 3. Configure environment variables

Create a `.env` file in the project root. You can use `.env.example` as
a reference:

``` bash
cp .env.example .env
```

Add your credentials and database connection details:

``` env
# Language model
GROQ_API_KEY=your_groq_api_key
GROQ_MODEL=openai/gpt-oss-20b

# External information services
TAVILY_API_KEY=your_tavily_api_key
AVIATIONSTACK_API_KEY=your_aviationstack_api_key
OPENWEATHER_API_KEY=your_openweather_api_key

# PostgreSQL / LangGraph persistence
DATABASE_URL=postgresql://username:password@host:5432/database_name

# Optional Redis cache
REDIS_URL=redis://localhost:6379/0
CACHE_ENABLED=true

# Server
HOST=127.0.0.1
PORT=8000
RELOAD=true
```

#### Environment variables

  -------------------------------------------------------------------------
  Variable                  Required                Purpose
  ------------------------- ----------------------- -----------------------
  `GROQ_API_KEY`            Yes                     Authenticates
                                                    language-model requests

  `DATABASE_URL`            Yes for persistent trip PostgreSQL connection
                            sessions                used by the LangGraph
                                                    checkpointer

  `TAVILY_API_KEY`          For Tavily-backed       Web search and
                            research                information retrieval

  `AVIATIONSTACK_API_KEY`   For flight-related      Airport and airline
                            integration             information

  `OPENWEATHER_API_KEY`     For weather integration Weather and forecast
                                                    information

  `GROQ_MODEL`              Optional                Selects the Groq model

  `REDIS_URL`               Optional                Redis connection for
                                                    caching

  `CACHE_ENABLED`           Optional                Enables or disables
                                                    caching

  `HOST`                    Optional                Server bind address

  `PORT`                    Optional                Server port

  `RELOAD`                  Optional                Enables development
                                                    reload behavior
  -------------------------------------------------------------------------

Keep your real `.env` file private. **Never commit API keys, passwords,
or database credentials to GitHub.**

### 4. Start the application

``` bash
uv run python app.py
```

Open the application in your browser:

``` text
http://127.0.0.1:8000
```

### Optional: Run with Docker

The repository includes a `Dockerfile` and `docker-compose.yml`. Review
the compose configuration and `.env.example`, configure the required
environment variables, and then run:

``` bash
docker compose up --build
```

------------------------------------------------------------------------

## 🔌 Main Pages and API Endpoints

  -------------------------------------------------------------------------------
  Page / Endpoint                 Method                  Purpose
  ------------------------------- ----------------------- -----------------------
  `/`                             GET                     Main conversational
                                                          travel planner

  `/budget`                       GET                     Budget Analyzer
                                                          interface

  `/api/budget/analyze`           POST                    Analyze a budget and
                                                          expense breakdown

  `/api/budget/estimate-trip`     POST                    Generate editable trip
                                                          budget estimates

  `/route-planner`                GET                     Day-wise route planner
                                                          interface

  `/api/itinerary/optimize`       POST                    Optimize an attraction
                                                          route

  `/api/itinerary/plan-options`   POST                    Generate itinerary
                                                          options

  `/api/travel`                   POST                    Submit a
                                                          travel-planning request

  `/health`                       GET                     Application health
                                                          check
  -------------------------------------------------------------------------------

Interactive API documentation may be available at:

``` text
http://127.0.0.1:8000/docs
```

### Example: Route optimizer request

`POST /api/itinerary/optimize`

``` json
{
  "hotel": {
    "lat": 28.6139,
    "lon": 77.2090
  },
  "start_time": "09:00",
  "end_time": "19:00",
  "average_speed_kmh": 25,
  "attractions": [
    {
      "id": "museum",
      "name": "Example Museum",
      "area": "Old Town",
      "lat": 28.615,
      "lon": 77.210,
      "visit_minutes": 90,
      "open_time": "09:00",
      "close_time": "17:00"
    },
    {
      "id": "market",
      "name": "Example Market",
      "area": "Old Town",
      "lat": 28.617,
      "lon": 77.212,
      "visit_minutes": 60,
      "open_time": "10:00",
      "close_time": "19:00"
    }
  ],
  "travel_times": {
    "__hotel__->museum": 8,
    "museum->market": 6,
    "market->__hotel__": 9
  }
}
```

The `travel_times` field is optional. When supplied, it can contain
directional travel-time estimates in minutes using the `from_id->to_id`
format. The hotel node identifier is `__hotel__`.

------------------------------------------------------------------------

## 🧪 Testing

Run the automated test suite from the project root:

``` bash
uv run python -m unittest discover -s tests -v
```

The included tests cover the budget analysis and route optimization
modules, including budget-profile behavior and route feasibility.

External-service behavior involving live language-model calls, Tavily,
AviationStack, OpenWeather, PostgreSQL, or Redis may require valid
credentials and separately configured services. A passing local unit
test suite does not by itself verify every external integration.

------------------------------------------------------------------------

## ⚠️ Limitations and Notes

-   Flight, hotel, weather, and attraction information depends on the
    configured providers and their API responses.
-   AI-generated budget estimates are planning estimates, not confirmed
    quotes or guaranteed prices.
-   Selecting a different currency does not automatically convert
    existing expense values using live exchange rates.
-   Route distances may be straight-line estimates when road-routing
    data is unavailable.
-   Estimated travel times are not guaranteed real-world journey times.
-   Attraction opening hours and coordinates should be checked before
    travel.
-   Route feasibility depends on the completeness and accuracy of the
    supplied attraction, hotel, and timing data.

------------------------------------------------------------------------

## 🛣️ Future Improvements

Potential areas for further development include:

-   Integration with verified road and public-transport routing data.
-   Live currency conversion and localized price estimation.
-   More advanced geographic clustering and multi-day route balancing.
-   Improved handling of uncertain attraction opening hours.
-   More comprehensive integration and end-to-end testing.
-   User accounts, trip sharing, and collaborative itinerary editing.

------------------------------------------------------------------------

## 🤝 Contributing

Contributions, suggestions, and bug reports are welcome.

1.  Fork the repository.

2.  Create a feature branch:

    ``` bash
    git checkout -b feature/your-feature-name
    ```

3.  Make your changes and add or update tests.

4.  Run the test suite.

5.  Commit and push your changes:

    ``` bash
    git add .
    git commit -m "Describe your changes"
    git push origin feature/your-feature-name
    ```

6.  Open a Pull Request with a clear explanation of the changes.

Please do not include secrets, API keys, or private configuration files
in commits.

------------------------------------------------------------------------

## 📄 License

This project is licensed under the **GNU General Public License v3.0
(GPL-3.0)**. See the [LICENSE](LICENSE) file for details.

------------------------------------------------------------------------

## 🙌 Acknowledgements

TravelBrain builds on the work of several open-source tools and service
providers:

-   [LangGraph](https://www.langchain.com/langgraph) and
    [LangChain](https://www.langchain.com/) for agent orchestration and
    LLM application components.
-   [Groq](https://groq.com/) for language-model inference.
-   [Tavily](https://tavily.com/) for web research.
-   [AviationStack](https://aviationstack.com/) for aviation
    information.
-   [OpenWeather](https://openweathermap.org/) for weather information.
-   [FastAPI](https://fastapi.tiangolo.com/) for the backend framework.

------------------------------------------------------------------------

<div align="center">
  <h3>TravelBrain — Plan less. Explore more. ✈️</h3>
</div>
=======
# TravelBean
AI-powered multi-agent travel planning system with A* route optimization and intelligent budget analysis
>>>>>>> 0c510bcafaf96fa0c62563a7bda45c87950126c6
