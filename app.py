import os
from pathlib import Path
import traceback
import re
import json
import uvicorn

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from src.api.sessions import (
    SESSION_COOKIE,
    SESSION_TTL_SECONDS,
    clear_credentials,
    get_credentials_for,
    new_session_id,
    store_credentials,
)
from src.api.validation import check_database_url, check_groq_api_key
from src.clients import cache
from src.config.session import (
    MissingCredentialsError,
    credential_status,
    use_credentials,
)
from src.config.settings import COOKIE_SAMESITE, COOKIE_SECURE, CORS_ORIGINS
from src.graph.runner import run_travel_agent
from src.budget_analyzer import analyze_budget
from src.route_optimizer import optimize_itinerary
from src.mcp_servers.remote import tavily_mcp_search
from src.clients.llm import get_llm

# This is to allow nested event loops for async calls in FastAPI
import nest_asyncio
nest_asyncio.apply()


BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR / "frontend"

app = FastAPI(
    title="TravelBrain AI",
    description="LangGraph Multi-Agent Travel Planner with FastAPI Frontend",
    version="1.0.0"
)


# Only needed when the browser talks to this API on a different origin. With
# the Vercel rewrite the frontend is same-origin, so this stays inactive.
if CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type"],
    )


app.mount(
    "/static",
    StaticFiles(directory=str(FRONTEND_DIR / "static")),
    name="static"
)


templates = Jinja2Templates(
    directory=str(FRONTEND_DIR / "templates")
)



class TravelRequest(BaseModel):
    message: str
    thread_id: str | None = None
    currency: str = "INR"


class BudgetAnalysisRequest(BaseModel):
    budget: float = Field(gt=0)
    costs: dict[str, float] = Field(default_factory=dict)
    profile: str = "balanced"
    currency: str = "INR"
    trip_context: str = ""
    duration_days: int | None = Field(default=None, ge=1, le=365)


class AttractionRouteRequest(BaseModel):
    hotel: dict
    attractions: list[dict] = Field(default_factory=list)
    start_time: str = "09:00"
    end_time: str = "19:00"
    average_speed_kmh: float = Field(default=25.0, gt=0)
    travel_times: dict[str, float] = Field(default_factory=dict)
    buffer_minutes: int = Field(default=15, ge=0, le=120)
    meal_break_minutes: int = Field(default=60, ge=0, le=180)
    currency: str = "INR"
    trip_context: str = ""


class ConfigRequest(BaseModel):
    """
    None leaves a field untouched, "" clears it. Keys are held in server
    memory for this session only and are never echoed back.
    """

    groq_api_key: str | None = None
    database_url: str | None = None



def _session_id(request: Request) -> str | None:
    return request.cookies.get(SESSION_COOKIE)


def _set_session_cookie(response: Response, session_id: str) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        session_id,
        max_age=SESSION_TTL_SECONDS,
        httponly=True,
        samesite=COOKIE_SAMESITE,
        secure=COOKIE_SECURE,
    )



@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={}
    )


# =========================
# Credentials
# =========================

@app.get("/budget", response_class=HTMLResponse)
async def budget_page(request: Request):
    return templates.TemplateResponse(request=request, name="budget.html")


@app.post("/api/budget/analyze")
async def budget_analysis(body: BudgetAnalysisRequest):
    try:
        result = analyze_budget(body.budget, body.costs, body.profile, currency=body.currency, trip_context=body.trip_context, duration_days=body.duration_days)
        return JSONResponse(content=result)
    except ValueError as error:
        return JSONResponse(status_code=400, content={"error": str(error)})



@app.post("/api/budget/estimate-trip")
async def estimate_trip_budget(request: Request, body: dict):
    # Use the current trip conversation to suggest editable category estimates.
    try:
        trip_context = str(body.get("trip_context") or "").strip()
        if not trip_context:
            return JSONResponse(status_code=400, content={"error": "No trip context was provided. Start a trip in the main chat first."})
        currency = str(body.get("currency") or "INR").upper()
        if currency not in {"INR", "USD", "EUR", "GBP", "AED", "JPY"}:
            return JSONResponse(status_code=400, content={"error": "Unsupported currency preference."})
        profile = str(body.get("profile") or "balanced")
        duration_days = max(1, min(365, int(body.get("duration_days") or 5)))
        travellers = max(1, min(50, int(body.get("travellers") or 1)))
        credentials = get_credentials_for(_session_id(request))
        prompt = ("Estimate a realistic planning budget for the trip described below. Use " + currency + " consistently. "
                  "Do not switch currencies. This is not a live quote.\nTrip conversation and plan: " + trip_context[:7000] +
                  f"\nTravel profile: {profile}. Duration: {duration_days} days. Travellers: {travellers}.\n" +
                  "Return ONLY JSON with keys budget, costs, assumptions. costs must include numeric values for travel, accommodation, food, local_transport, activities, miscellaneous. "
                  "budget must be at least the sum of costs. Use sensible broad estimates for destination and duration; don't invent booked prices. "
                  "assumptions must be an array of short strings describing unknowns and estimation basis. Return numbers only, no currency symbols.")
        with use_credentials(credentials):
            response = await get_llm().ainvoke(prompt)
        content = str(getattr(response, "content", response)).strip()
        content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content, flags=re.I)
        estimate = json.loads(content)
        costs = estimate.get("costs") or {}
        required = {"travel", "accommodation", "food", "local_transport", "activities", "miscellaneous"}
        if not required.issubset(costs) or "budget" not in estimate:
            raise ValueError("The estimate was missing required budget categories.")
        for key in required | {"budget"}:
            value = estimate["budget"] if key == "budget" else costs[key]
            if not isinstance(value, (int, float)) or not __import__("math").isfinite(value) or value < 0:
                raise ValueError("The estimate contained invalid amounts.")
        normalized_costs = {k: float(costs[k]) for k in required}
        suggested_budget = max(float(estimate["budget"]), sum(normalized_costs.values()))
        return JSONResponse(content={"currency": currency, "budget": suggested_budget, "costs": normalized_costs, "assumptions": estimate.get("assumptions", []), "duration_days": duration_days, "travellers": travellers, "disclaimer": "AI-generated planning estimate, not live quotes. Review and adjust all amounts before relying on them."})
    except MissingCredentialsError as error:
        return JSONResponse(status_code=428, content={"error": str(error), "missing": error.missing})
    except (json.JSONDecodeError, ValueError) as error:
        return JSONResponse(status_code=502, content={"error": f"Could not validate a budget estimate: {error}"})
    except Exception as error:
        traceback.print_exc()
        return JSONResponse(status_code=502, content={"error": f"Could not estimate the trip budget: {error}"})


@app.get("/route-planner", response_class=HTMLResponse)
async def route_planner_page(request: Request):
    return templates.TemplateResponse(request=request, name="route_planner.html")


@app.post("/api/itinerary/optimize")
async def itinerary_optimization(body: AttractionRouteRequest):
    try:
        result = optimize_itinerary(
            body.hotel, body.attractions, body.start_time, body.end_time,
            average_speed_kmh=body.average_speed_kmh, travel_times=body.travel_times, buffer_minutes=body.buffer_minutes, meal_break_minutes=body.meal_break_minutes,
        )
        return JSONResponse(content=result)
    except ValueError as error:
        return JSONResponse(status_code=400, content={"error": str(error)})



@app.post("/api/itinerary/plan-options")
async def itinerary_plan_options(request: Request, body: dict):
    # Use existing Tavily research and LLM to prepare customer-facing itinerary options.
    try:
        destination = str(body.get("destination") or "").strip()
        trip_context = str(body.get("trip_context") or "").strip()
        attraction_names = body.get("attractions") or []
        if isinstance(attraction_names, str):
            attraction_names = [line.strip() for line in attraction_names.splitlines() if line.strip()]
        attraction_names = [str(x).strip() for x in attraction_names if str(x).strip()][:16]
        if not destination:
            return JSONResponse(status_code=400, content={"error": "Add the destination from your trip first."})
        if not attraction_names:
            return JSONResponse(status_code=400, content={"error": "Add at least one attraction you want to visit."})
        hotel_name = str(body.get("hotel_name") or "hotel in " + destination).strip()
        start_time = str(body.get("start_time") or "09:00")
        end_time = str(body.get("end_time") or "19:00")
        currency = str(body.get("currency") or "INR").upper()
        profile = str(body.get("profile") or "balanced")
        buffer_minutes = max(0, min(120, int(body.get("buffer_minutes", 20))))
        research_query = (f"{destination} attraction visitor information opening hours coordinates "
                          f"{', '.join(attraction_names)}; famous local restaurants and food places near these attractions")
        credentials = get_credentials_for(_session_id(request))
        with use_credentials(credentials):
            research = await tavily_mcp_search(research_query)
        prompt = f'''Prepare structured travel data for an itinerary optimizer. Use research as grounding and do not claim uncertain details are verified.
Destination: {destination}
Hotel/base: {hotel_name}
Selected attractions (do not silently drop any): {json.dumps(attraction_names, ensure_ascii=False)}
Current trip conversation: {trip_context[:5000]}
Web research: {str(research)[:14000]}
Daily sightseeing window: {start_time} to {end_time}. Travel profile: {profile}. Currency: {currency}.
Return ONLY a valid JSON object with keys destination, hotel, attractions, food_places, notes.
hotel: lat, lon, location_label, coordinate_confidence.
Each attraction: id, name, area, lat, lon, visit_minutes, open_time, close_time, hours_confidence, coordinate_confidence, source_note. Use 24-hour time. If data is missing, use null rather than invent a verified fact. If estimating coordinates or opening hours, set confidence to "estimated" and mention it in source_note.
food_places: 4-8 well-known food places near the selected attractions where research supports it; fields name, area, specialty, meal, price_level, source_note. Do not invent exact prices.
notes: explain any missing or estimated data.'''
        with use_credentials(credentials):
            response = await get_llm().ainvoke(prompt)
        content = str(getattr(response, "content", response)).strip()
        content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content, flags=re.I)
        data = json.loads(content)
        hotel = data.get("hotel") or {}
        if hotel.get("lat") is None or hotel.get("lon") is None:
            return JSONResponse(status_code=422, content={"error": "I couldn't determine the hotel location. Add the hotel name or address to the main trip chat and try again.", "research_notes": data.get("notes", [])})
        raw_stops = data.get("attractions") or []
        usable = [x for x in raw_stops if x.get("lat") is not None and x.get("lon") is not None and x.get("open_time") and x.get("close_time")]
        missing = [str(x.get("name", "Selected attraction")) for x in raw_stops if x not in usable]
        if len(usable) != len(attraction_names):
            return JSONResponse(status_code=422, content={"error": "Some selected places are missing location or opening-hour details, so I can't safely schedule every stop yet.", "missing_details": missing, "food_places": data.get("food_places", []), "research_notes": data.get("notes", []), "destination": destination})
        options = []
        for option_name, extra_buffer, meal_break in [("Efficient day", max(10, buffer_minutes), 45), ("Balanced day", max(20, buffer_minutes + 10), 60), ("Relaxed pace", max(30, buffer_minutes + 25), 75)]:
            route_result = optimize_itinerary({"lat": float(hotel["lat"]), "lon": float(hotel["lon"])}, usable, start_time, end_time, buffer_minutes=extra_buffer, meal_break_minutes=meal_break)
            total_minutes = sum((d.get("total_travel_minutes") or 0) + (d.get("total_visit_minutes") or 0) + d.get("total_buffer_minutes", 0) for d in route_result.get("days", []))
            options.append({"name": option_name, "buffer_minutes": extra_buffer, "meal_break_minutes": meal_break, "total_duration_minutes": total_minutes, "feasible": route_result["feasible"], "route": route_result, "summary": route_result.get("explanation", "")})
        return JSONResponse(content={"destination": destination, "currency": currency, "options": options, "food_places": data.get("food_places", []), "notes": data.get("notes", []), "selected_count": len(attraction_names), "travel_time_notice": "Distances and travel times are estimates from researched or estimated coordinates and fallback speed, not live road-routing results."})
    except MissingCredentialsError as error:
        return JSONResponse(status_code=428, content={"error": str(error), "missing": error.missing})
    except json.JSONDecodeError:
        return JSONResponse(status_code=502, content={"error": "The research response could not be structured safely. Please try again."})
    except Exception as error:
        traceback.print_exc()
        return JSONResponse(status_code=502, content={"error": f"Could not prepare itinerary options: {str(error)}"})


@app.get("/api/config")
async def read_config(request: Request):
    """What is configured, and where it came from. Never returns a secret."""

    credentials = get_credentials_for(_session_id(request))

    with use_credentials(credentials):
        return JSONResponse(content=credential_status())


@app.post("/api/config")
async def write_config(request: Request, body: ConfigRequest):
    """
    Store credentials for this browser session. Each supplied value is
    checked against the real service before being accepted.
    """

    session_id = _session_id(request) or new_session_id()

    errors = {}

    groq_key = (body.groq_api_key or "").strip()
    if groq_key:
        ok, detail = check_groq_api_key(groq_key)
        if not ok:
            errors["groq_api_key"] = detail

    database_url = (body.database_url or "").strip()
    if database_url:
        ok, detail = check_database_url(database_url)
        if not ok:
            errors["database_url"] = detail

    if errors:
        response = JSONResponse(
            status_code=400,
            content={"success": False, "errors": errors},
        )
        _set_session_cookie(response, session_id)
        return response

    credentials = store_credentials(
        session_id,
        groq_api_key=body.groq_api_key,
        database_url=body.database_url,
    )

    with use_credentials(credentials):
        payload = {"success": True, **credential_status()}

    response = JSONResponse(content=payload)
    _set_session_cookie(response, session_id)

    return response


@app.delete("/api/config")
async def reset_config(request: Request):
    """Drop session keys and fall back to whatever the server's .env has."""

    clear_credentials(_session_id(request))

    with use_credentials(None):
        return JSONResponse(content={"success": True, **credential_status()})


# =========================
# Planning
# =========================

@app.post("/api/travel")
async def travel_planner(request: Request, request_data: TravelRequest):
    credentials = get_credentials_for(_session_id(request))

    try:
        user_message = request_data.message.strip()
        currency = (request_data.currency or "INR").upper()
        if currency not in {"INR", "USD", "EUR", "GBP", "AED", "JPY"}:
            return JSONResponse(status_code=400, content={"success": False, "error": "Unsupported currency preference."})
        if user_message:
            user_message += f"\n\nIMPORTANT TRIP CURRENCY PREFERENCE: Present all budget estimates, prices, and spending recommendations consistently in {currency}. Do not switch to USD unless USD is selected. Label estimates and distinguish them from live prices."

        if not user_message:
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "error": "Message cannot be empty."
                }
            )

        with use_credentials(credentials):
            result = run_travel_agent(
                user_input=user_message,
                thread_id=request_data.thread_id
            )

        return JSONResponse(
            content={
                "success": True,
                "thread_id": result["thread_id"],
                "answer": result["answer"],
                "flight_results": result["flight_results"],
                "hotel_results": result["hotel_results"],
                "weather_results": result.get("weather_results", ""),
                "itinerary": result["itinerary"],
                "llm_calls": result["llm_calls"],
            }
        )

    except MissingCredentialsError as e:
        # The frontend turns this into a prompt to open Settings.
        return JSONResponse(
            status_code=428,
            content={
                "success": False,
                "error": str(e),
                "missing": e.missing,
            }
        )

    except Exception as e:
        print("ERROR:", e)
        traceback.print_exc()

        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": str(e)
            }
        )



@app.head("/", include_in_schema=False)
async def home_head():
    """Hosting platforms probe with HEAD to detect an open port."""

    return Response(status_code=200)


@app.api_route("/health", methods=["GET", "HEAD"])
async def health_check(request: Request):
    credentials = get_credentials_for(_session_id(request))

    with use_credentials(credentials):
        status = credential_status()

    return {
        "status": "ok",
        "message": "AI Travel Planner API is running",
        "ready": status["ready"],
        "missing": status["missing"],
        "cache": cache.status(),
    }


@app.get("/favicon.ico")
async def favicon():
    return JSONResponse(content={})



if __name__ == "__main__":
    # Defaults suit local development. In Docker, HOST is set to 0.0.0.0
    # so the port is reachable from outside the container.
    uvicorn.run(
        "app:app",
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "8000")),
        reload=os.getenv("RELOAD", "true").lower() not in ("false", "0", "no")
    )
