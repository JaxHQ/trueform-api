from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Any
import random
import pandas as pd
from datetime import datetime

app = FastAPI()

# --- CORS Setup ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Load Exercises from Google Sheets ---
CSV_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vQ04XU88PE6x8GET2SblG-f7Gx-XWTvClQqm5QOdQ_EE682yDqMHY25EcR3N7qjIwa5lM_S_azLaM6n/pub?gid=1956029134&single=true&output=csv"

EXERCISES = []

try:
    df = pd.read_csv(CSV_URL)
    print(f"✅ Loaded {len(df)} exercises from Google Sheets.")

    for _, row in df.iterrows():
        EXERCISES.append({
            "name": row.get("Exercise Name", "").strip(),
            "muscleGroup": row.get("Primary Muscle Group", "").strip(),
            "movementType": row.get("Movement Type", "").strip(),
            "equipment": [e.strip() for e in str(row.get("Equipment Used", "")).split(",")],
            "archetypes": [a.strip() for a in str(row.get("Archetype Tags", "")).split(",")],
            "otherTags": [t.strip() for t in str(row.get("Other Tags", "")).split(",")],
            "bodyRegion": row.get("Body Region", "").strip()
        })

except Exception as e:
    print("❌ Failed to load exercise list from Google Sheets:", e)

REST_TIME_DEFAULT = 60
user_logs = {}

# --- Models ---
class WorkoutRequest(BaseModel):
    daysPerWeek: int
    availableTime: int
    lastWorked: Dict[str, int]
    weeklyVolume: Dict[str, int]
    equipmentAccess: List[str]
    archetype: Optional[str] = Field(default=None)
    userPrefs: Optional[List[str]] = Field(default_factory=list)
    injuries: Optional[List[str]] = Field(default_factory=list)
    focus: Optional[str] = Field(default="Full Body")
    prepType: Optional[str] = Field(default="Skip")
    goal: Optional[str] = Field(default=None)

class ExerciseOut(BaseModel):
    name: str
    muscleGroup: str
    movementType: str
    sets: int
    reps: str
    rest: int
    alternatives: List[str]
    suggestion: Optional[str] = None

class WorkoutLog(BaseModel):
    userId: str
    date: str
    exercises: List[Dict[str, Any]]
    duration: int

# --- Helpers ---
def check_for_static_weights(logs: dict):
    suggestions = {}
    for exercise_id, entries in logs.items():
        if len(entries) < 3:
            continue
        last_3_weights = [tuple(entry["weights"]) for entry in entries[-3:]]
        if all(w == last_3_weights[0] for w in last_3_weights):
            suggestions[exercise_id] = "You've used the same weight 3 sessions in a row. Try increasing slightly."
    return suggestions

def try_filter(data, movement=None, relax_focus=False):
    return [
        ex for ex in EXERCISES
        if data.archetype in ex["archetypes"]
        and any(eq in data.equipmentAccess for eq in ex["equipment"])
        and (not movement or ex["movementType"] == movement)
        and (relax_focus or data.focus == "Full Body" or ex["bodyRegion"] == data.focus)
        and not any(pref.lower() in ex["name"].lower() for pref in data.userPrefs)
    ]

# --- Endpoints ---
@app.post("/generate-workout", response_model=List[ExerciseOut])
def generate_workout(data: WorkoutRequest):
    if not data.archetype:
        raise HTTPException(status_code=400, detail="Archetype is required.")

    time_budget = data.availableTime
    suggestions = check_for_static_weights(user_logs)
    workout = []

    # 1. Warm-up block
    if data.prepType in ["Warm-Up", "Both"] and time_budget >= 10:
        warmups = try_filter(data, movement="Warm-Up")
        if warmups:
            warmup = random.choice(warmups)
            workout.append(warmup)
            time_budget -= 10

    # 2. Main exercise blocks
    num_main_blocks = max(1, time_budget // 10)
    main_pool = try_filter(data)

    if len(main_pool) < num_main_blocks:
        main_pool = try_filter(data, relax_focus=True)

    if len(main_pool) < num_main_blocks:
        main_pool = [
            ex for ex in EXERCISES
            if data.archetype in ex["archetypes"]
            and any(eq in data.equipmentAccess for eq in ex["equipment"])
            and not any(pref.lower() in ex["name"].lower() for pref in data.userPrefs)
        ]

    selected_main = random.sample(main_pool, min(num_main_blocks, len(main_pool)))
    workout.extend(selected_main)
    time_budget -= 10 * len(selected_main)

    # 3. Conditioning block
    if data.prepType in ["Conditioning", "Both"] and time_budget >= 10:
        conditioning = try_filter(data, movement="Conditioning", relax_focus=True)
        if conditioning:
            workout.append(random.choice(conditioning))
            time_budget -= 10

    # 4. Format for frontend
    output = []
    for ex in workout:
        ex_id = ex["name"].lower().replace(" ", "-")
        alts = [
            alt["name"] for alt in EXERCISES
            if alt["name"] != ex["name"]
            and alt["muscleGroup"] == ex["muscleGroup"]
            and alt["movementType"] == ex["movementType"]
        ]
        output.append({
            "name": ex["name"],
            "muscleGroup": ex["muscleGroup"],
            "movementType": ex["movementType"],
            "sets": 4,
            "reps": "8-12",
            "rest": REST_TIME_DEFAULT,
            "alternatives": random.sample(alts, min(3, len(alts))),
            "suggestion": suggestions.get(ex_id)
        })

    return output

@app.post("/reshuffle-exercise", response_model=ExerciseOut)
def reshuffle_exercise(data: dict):
    current_name = data.get("currentName")
    muscle_group = data.get("muscleGroup")
    equipment = data.get("equipmentAccess", [])
    user_prefs = data.get("userPrefs", [])
    archetype = data.get("archetype")
    same_muscle = data.get("sameMuscle", True)

    pool = [
        ex for ex in EXERCISES
        if ex["name"] != current_name
        and (not same_muscle or ex["muscleGroup"] == muscle_group)
        and any(e in equipment for e in ex["equipment"])
        and not any(pref.lower() in ex["name"].lower() for pref in user_prefs)
        and (not archetype or archetype in ex["archetypes"])
    ]

    if not pool:
        raise HTTPException(status_code=404, detail="No suitable alternatives found.")

    new_ex = random.choice(pool)
    alts = [
        alt["name"] for alt in pool
        if alt["name"] != new_ex["name"]
        and alt["muscleGroup"] == new_ex["muscleGroup"]
        and alt["movementType"] == new_ex["movementType"]
    ]

    return {
        "name": new_ex["name"],
        "muscleGroup": new_ex["muscleGroup"],
        "movementType": new_ex["movementType"],
        "sets": 4,
        "reps": "8-12",
        "rest": REST_TIME_DEFAULT,
        "alternatives": random.sample(alts, min(3, len(alts))),
        "suggestion": None
    }
