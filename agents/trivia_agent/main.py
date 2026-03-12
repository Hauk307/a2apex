"""
Trivia A2A Agent - Returns random trivia facts from a curated list.

Run with: python3 -m uvicorn agents.trivia_agent.main:app --port 8095
"""

import uuid
import random
from datetime import datetime
from typing import Any
from enum import Enum

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse


# ============================================================================
# APP SETUP
# ============================================================================

app = FastAPI(
    title="Trivia Agent",
    description="Returns random trivia facts",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# DATA MODELS
# ============================================================================

class TaskState(str, Enum):
    SUBMITTED = "submitted"
    WORKING = "working"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"


class Task:
    def __init__(self, task_id: str, context_id: str, message: dict):
        self.id = task_id
        self.context_id = context_id
        self.state = TaskState.SUBMITTED
        self.created_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()
        self.messages = [message]
        self.artifacts = []
        self.history = []
        self.metadata = {}

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "contextId": self.context_id,
            "status": {
                "state": self.state.value,
                "timestamp": self.updated_at.isoformat() + "Z"
            },
            "artifacts": self.artifacts,
            "history": self.history,
            "metadata": self.metadata,
            "kind": "task"
        }

    def update_state(self, state: TaskState):
        self.state = state
        self.updated_at = datetime.utcnow()


tasks: dict[str, Task] = {}


# ============================================================================
# AGENT CARD
# ============================================================================

AGENT_CARD = {
    "name": "Trivia Agent",
    "description": "Returns random trivia facts across various categories including science, history, animals, space, and more. Great for learning something new!",
    "url": "http://localhost:8095/a2a",
    "version": "1.0.0",
    "protocolVersion": "0.3.0",
    "preferredTransport": "JSONRPC",
    "capabilities": {
        "streaming": False,
        "pushNotifications": False,
        "stateTransitionHistory": True
    },
    "defaultInputModes": ["text/plain"],
    "defaultOutputModes": ["text/plain", "application/json"],
    "skills": [
        {
            "id": "trivia",
            "name": "Random Trivia",
            "description": "Get a random trivia fact. Optionally specify a category: science, history, animals, space, food, geography, sports, or technology.",
            "tags": ["trivia", "facts", "fun", "education"],
            "examples": [
                "Give me a trivia fact",
                "Trivia about space",
                "Random animal fact",
                "Tell me something about history"
            ],
            "inputModes": ["text/plain"],
            "outputModes": ["text/plain", "application/json"]
        }
    ],
    "securitySchemes": {},
    "security": [],
    "provider": {
        "organization": "A2Apex Demo",
        "url": "https://app.a2apex.io"
    }
}


@app.get("/.well-known/agent.json")
@app.get("/.well-known/agent-card.json")
async def get_agent_card():
    return JSONResponse(content=AGENT_CARD)


# ============================================================================
# TRIVIA DATABASE
# ============================================================================

TRIVIA_FACTS = {
    "science": [
        {"fact": "A single bolt of lightning contains enough energy to toast 100,000 slices of bread.", "source": "National Geographic"},
        {"fact": "Honey never spoils. Archaeologists have found 3,000-year-old honey in Egyptian tombs that was still edible.", "source": "Smithsonian"},
        {"fact": "Octopuses have three hearts and blue blood.", "source": "National Oceanic and Atmospheric Administration"},
        {"fact": "A day on Venus is longer than its year.", "source": "NASA"},
        {"fact": "Bananas are berries, but strawberries aren't.", "source": "Botanical Society"},
        {"fact": "Water can boil and freeze at the same time (at the triple point).", "source": "Chemistry Journal"},
        {"fact": "The human brain uses roughly the same amount of power as a 10-watt light bulb.", "source": "Scientific American"},
        {"fact": "Glass is technically a liquid that flows very, very slowly.", "source": "Physics Today"},
    ],
    "history": [
        {"fact": "Cleopatra lived closer in time to the Moon landing than to the construction of the Great Pyramid.", "source": "Historical Records"},
        {"fact": "Oxford University is older than the Aztec Empire.", "source": "Oxford Archives"},
        {"fact": "The shortest war in history lasted 38-45 minutes (Britain vs Zanzibar, 1896).", "source": "Guinness World Records"},
        {"fact": "Vikings used the bones of slain animals to make their boats.", "source": "Viking Museum"},
        {"fact": "Ancient Romans used crushed mouse brains as toothpaste.", "source": "Roman Historical Society"},
        {"fact": "The Great Fire of London in 1666 officially killed only 6 people.", "source": "London Historical Archive"},
        {"fact": "Napoleon was once attacked by a horde of rabbits during a hunt.", "source": "French Historical Records"},
        {"fact": "The first computer programmer was a woman: Ada Lovelace in the 1840s.", "source": "Computing History Museum"},
    ],
    "animals": [
        {"fact": "A group of flamingos is called a 'flamboyance'.", "source": "Ornithological Society"},
        {"fact": "Cows have best friends and get stressed when separated.", "source": "Animal Behavior Journal"},
        {"fact": "A snail can sleep for three years.", "source": "Marine Biology Institute"},
        {"fact": "Elephants are the only animals that can't jump.", "source": "Wildlife Foundation"},
        {"fact": "A shrimp's heart is located in its head.", "source": "Marine Science Review"},
        {"fact": "Sloths can hold their breath longer than dolphins (up to 40 minutes).", "source": "Wildlife Journal"},
        {"fact": "Butterflies taste with their feet.", "source": "Entomology Today"},
        {"fact": "A rhinoceros's horn is made of hair.", "source": "Zoological Society"},
    ],
    "space": [
        {"fact": "There are more stars in the universe than grains of sand on Earth.", "source": "NASA"},
        {"fact": "A year on Mercury is just 88 Earth days.", "source": "Planetary Science Institute"},
        {"fact": "Neutron stars are so dense that a teaspoon would weigh about 6 billion tons.", "source": "Astrophysical Journal"},
        {"fact": "The footprints on the Moon will be there for 100 million years.", "source": "NASA"},
        {"fact": "Space is completely silent because there's no atmosphere to carry sound.", "source": "European Space Agency"},
        {"fact": "One day on Mars is 24 hours and 37 minutes, almost like Earth.", "source": "Mars Exploration Program"},
        {"fact": "There's a planet made of diamonds twice the size of Earth (55 Cancri e).", "source": "Yale University"},
        {"fact": "The sun makes up 99.86% of the mass in our solar system.", "source": "Solar Physics Journal"},
    ],
    "food": [
        {"fact": "Peanuts aren't nuts - they're legumes.", "source": "Food Science Institute"},
        {"fact": "Ketchup was sold as medicine in the 1830s.", "source": "Culinary History Archive"},
        {"fact": "Apples float because they're 25% air.", "source": "Agricultural Research"},
        {"fact": "The most expensive pizza in the world costs $12,000.", "source": "Guinness World Records"},
        {"fact": "Carrots were originally purple before the 17th century.", "source": "World Carrot Museum"},
        {"fact": "Chocolate was once used as currency by the Aztecs.", "source": "Food History Journal"},
        {"fact": "A cucumber is 95% water.", "source": "USDA"},
        {"fact": "There are over 7,500 varieties of apples worldwide.", "source": "Apple Research Council"},
    ],
    "geography": [
        {"fact": "Russia has 11 time zones.", "source": "World Atlas"},
        {"fact": "Canada has more lakes than the rest of the world combined.", "source": "Geographical Survey"},
        {"fact": "Australia is wider than the Moon.", "source": "NASA"},
        {"fact": "Vatican City is the smallest country in the world.", "source": "United Nations"},
        {"fact": "The Dead Sea is the lowest point on Earth's surface.", "source": "Geological Society"},
        {"fact": "There's a town in Norway called Hell, and it freezes over every winter.", "source": "Norwegian Tourism"},
        {"fact": "Mt. Everest grows about 4 millimeters every year.", "source": "Geological Survey"},
        {"fact": "Africa is the only continent in all four hemispheres.", "source": "World Geography Institute"},
    ],
    "sports": [
        {"fact": "A golf ball has 336 dimples.", "source": "PGA"},
        {"fact": "The Olympics used to award medals for art.", "source": "Olympic Committee"},
        {"fact": "A baseball has exactly 108 stitches.", "source": "MLB"},
        {"fact": "The first basketball hoops were actually peach baskets.", "source": "Basketball Hall of Fame"},
        {"fact": "Tennis players can run up to 3 miles during a single match.", "source": "ATP"},
        {"fact": "The longest tennis match lasted 11 hours and 5 minutes.", "source": "Wimbledon Archives"},
        {"fact": "Tug of war was an Olympic sport until 1920.", "source": "Olympic History"},
        {"fact": "The average lifespan of an MLB baseball is 7 pitches.", "source": "Baseball Research"},
    ],
    "technology": [
        {"fact": "The first computer virus was created in 1983, called 'Elk Cloner'.", "source": "Computer History Museum"},
        {"fact": "The first ever website is still online (info.cern.ch).", "source": "CERN"},
        {"fact": "Email existed before the World Wide Web.", "source": "Internet History"},
        {"fact": "The average smartphone has more computing power than NASA had in 1969.", "source": "IEEE"},
        {"fact": "QWERTY keyboards were designed to slow typists down.", "source": "Typing History"},
        {"fact": "The first 1GB hard drive weighed 550 pounds and cost $40,000.", "source": "IBM Archives"},
        {"fact": "92% of the world's currency exists only digitally.", "source": "Federal Reserve"},
        {"fact": "The moon landing had less computing power than a modern calculator.", "source": "NASA"},
    ],
}


def get_trivia(category: str = None, original_query: str = "") -> tuple[str, list]:
    """Get a random trivia fact, optionally from a specific category."""
    matched = False
    if category and category.lower() in TRIVIA_FACTS:
        cat = category.lower()
        matched = True
    else:
        cat = random.choice(list(TRIVIA_FACTS.keys()))
    
    # Get random fact from category
    fact_data = random.choice(TRIVIA_FACTS[cat])
    
    # Format response
    emoji_map = {
        "science": "🔬",
        "history": "📜",
        "animals": "🦁",
        "space": "🚀",
        "food": "🍕",
        "geography": "🌍",
        "sports": "⚽",
        "technology": "💻"
    }
    emoji = emoji_map.get(cat, "💡")
    
    if matched:
        response = f"{emoji} **{cat.title()} Trivia**\n\n{fact_data['fact']}\n\n📚 Source: {fact_data['source']}"
    else:
        response = f"I don't have a specific answer for that, but here's a fun {cat} fact!\n\n{emoji} **{cat.title()} Trivia**\n\n{fact_data['fact']}\n\n📚 Source: {fact_data['source']}\n\n💡 Try asking about: science, history, animals, space, food, geography, sports, or technology!"
    
    data = {
        "category": cat,
        "fact": fact_data["fact"],
        "source": fact_data["source"],
        "total_categories": len(TRIVIA_FACTS),
        "facts_in_category": len(TRIVIA_FACTS[cat])
    }
    
    artifacts = [{
        "artifactId": str(uuid.uuid4()),
        "name": "trivia-fact",
        "description": f"Random trivia fact from {cat}",
        "parts": [
            {"kind": "text", "text": response},
            {"kind": "data", "data": data}
        ]
    }]
    
    return response, artifacts


def detect_category(text: str) -> str:
    """Detect category from user input."""
    text_lower = text.lower()
    
    for category in TRIVIA_FACTS.keys():
        if category in text_lower:
            return category
    
    # Aliases — broad keyword matching
    aliases = {
        # animals
        "animal": "animals", "creature": "animals", "wildlife": "animals",
        "dog": "animals", "cat": "animals", "bird": "animals", "fish": "animals",
        "lion": "animals", "tiger": "animals", "bear": "animals", "elephant": "animals",
        "whale": "animals", "shark": "animals", "snake": "animals", "insect": "animals",
        "cheetah": "animals", "dolphin": "animals", "monkey": "animals", "gorilla": "animals",
        "spider": "animals", "bee": "animals", "ant": "animals", "cow": "animals",
        "horse": "animals", "pig": "animals", "deer": "animals", "wolf": "animals",
        "fox": "animals", "rabbit": "animals", "frog": "animals", "owl": "animals",
        # space
        "star": "space", "planet": "space", "astronomy": "space", "universe": "space",
        "moon": "space", "sun": "space", "galaxy": "space", "mars": "space",
        "jupiter": "space", "saturn": "space", "nasa": "space", "rocket": "space",
        "astronaut": "space", "orbit": "space", "comet": "space", "meteor": "space",
        "black hole": "space", "nebula": "space", "telescope": "space",
        # history
        "historical": "history", "past": "history", "ancient": "history",
        "war": "history", "king": "history", "queen": "history", "empire": "history",
        "roman": "history", "egyptian": "history", "medieval": "history", "viking": "history",
        "revolution": "history", "president": "history", "civilization": "history",
        "century": "history", "dynasty": "history", "castle": "history", "knight": "history",
        "bridge": "history", "london": "history", "napoleon": "history", "pyramid": "history",
        # science
        "scientific": "science", "physics": "science", "chemistry": "science",
        "biology": "science", "dna": "science", "atom": "science", "molecule": "science",
        "experiment": "science", "lab": "science", "element": "science", "energy": "science",
        "gravity": "science", "light": "science", "brain": "science", "cell": "science",
        "electric": "science", "magnet": "science", "oxygen": "science", "water": "science",
        # food
        "eating": "food", "cooking": "food", "cuisine": "food",
        "fruit": "food", "vegetable": "food", "pizza": "food", "chocolate": "food",
        "coffee": "food", "tea": "food", "bread": "food", "cheese": "food",
        "meat": "food", "rice": "food", "spice": "food", "sugar": "food",
        "recipe": "food", "restaurant": "food", "diet": "food", "nutrition": "food",
        # geography
        "country": "geography", "countries": "geography", "world": "geography",
        "continent": "geography", "ocean": "geography", "mountain": "geography",
        "river": "geography", "island": "geography", "desert": "geography",
        "city": "geography", "map": "geography", "border": "geography",
        "lake": "geography", "volcano": "geography", "forest": "geography",
        # technology
        "tech": "technology", "computer": "technology", "digital": "technology",
        "internet": "technology", "phone": "technology", "software": "technology",
        "hardware": "technology", "ai": "technology", "robot": "technology",
        "code": "technology", "programming": "technology", "app": "technology",
        "website": "technology", "wifi": "technology", "bluetooth": "technology",
        # sports
        "game": "sports", "athletic": "sports", "olympic": "sports",
        "baseball": "sports", "football": "sports", "soccer": "sports",
        "basketball": "sports", "tennis": "sports", "golf": "sports",
        "swimming": "sports", "running": "sports", "race": "sports",
        "fast": "sports", "speed": "sports", "team": "sports", "player": "sports",
        "ball": "sports", "score": "sports", "champion": "sports", "medal": "sports",
    }
    
    for alias, category in aliases.items():
        if alias in text_lower:
            return category
    
    return None


# ============================================================================
# JSON-RPC HELPERS
# ============================================================================

def make_jsonrpc_response(request_id: Any, result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def make_jsonrpc_error(request_id: Any, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


ERROR_CODES = {
    "parse_error": -32700,
    "invalid_request": -32600,
    "method_not_found": -32601,
    "invalid_params": -32602,
    "task_not_found": -32001,
}


# ============================================================================
# A2A ENDPOINT
# ============================================================================

@app.post("/a2a")
async def a2a_endpoint(request: Request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(content=make_jsonrpc_error(None, ERROR_CODES["parse_error"], "Parse error"))
    
    request_id = body.get("id")
    method = body.get("method")
    params = body.get("params", {})
    
    if body.get("jsonrpc") != "2.0":
        return JSONResponse(content=make_jsonrpc_error(request_id, ERROR_CODES["invalid_request"], "Invalid JSON-RPC version"))
    
    if method == "message/send":
        return await handle_message_send(request_id, params)
    elif method == "tasks/get":
        return await handle_tasks_get(request_id, params)
    elif method == "tasks/cancel":
        return await handle_tasks_cancel(request_id, params)
    else:
        return JSONResponse(content=make_jsonrpc_error(request_id, ERROR_CODES["method_not_found"], f"Method not found: {method}"))


async def handle_message_send(request_id: Any, params: dict) -> JSONResponse:
    message = params.get("message")
    if not message:
        return JSONResponse(content=make_jsonrpc_error(request_id, ERROR_CODES["invalid_params"], "message is required"))
    
    parts = message.get("parts", [])
    text_parts = [p.get("text", "") for p in parts if p.get("kind") == "text"]
    message_text = " ".join(text_parts).strip()
    
    context_id = message.get("contextId") or str(uuid.uuid4())
    task_id = str(uuid.uuid4())
    
    task = Task(task_id, context_id, message)
    tasks[task_id] = task
    
    task.update_state(TaskState.WORKING)
    
    try:
        category = detect_category(message_text)
        response_text, artifacts = get_trivia(category, message_text)
        task.artifacts = artifacts
        task.history = [
            message,
            {
                "role": "agent",
                "messageId": str(uuid.uuid4()),
                "parts": [{"kind": "text", "text": response_text}],
                "kind": "message"
            }
        ]
        task.update_state(TaskState.COMPLETED)
    except Exception as e:
        task.update_state(TaskState.FAILED)
        task.metadata["error"] = str(e)
    
    return JSONResponse(content=make_jsonrpc_response(request_id, task.to_dict()))


async def handle_tasks_get(request_id: Any, params: dict) -> JSONResponse:
    task_id = params.get("id")
    if not task_id or task_id not in tasks:
        return JSONResponse(content=make_jsonrpc_error(request_id, ERROR_CODES["task_not_found"], "Task not found"))
    return JSONResponse(content=make_jsonrpc_response(request_id, tasks[task_id].to_dict()))


async def handle_tasks_cancel(request_id: Any, params: dict) -> JSONResponse:
    task_id = params.get("id")
    if not task_id or task_id not in tasks:
        return JSONResponse(content=make_jsonrpc_error(request_id, ERROR_CODES["task_not_found"], "Task not found"))
    task = tasks[task_id]
    if task.state in [TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELED]:
        return JSONResponse(content=make_jsonrpc_error(request_id, -32002, "Task already in terminal state"))
    task.update_state(TaskState.CANCELED)
    return JSONResponse(content=make_jsonrpc_response(request_id, task.to_dict()))


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "trivia-agent", "version": "1.0.0"}


if __name__ == "__main__":
    import uvicorn
    print("🎯 Starting Trivia Agent on http://localhost:8095")
    uvicorn.run(app, host="0.0.0.0", port=8095)
