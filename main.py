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
            "workoutRole": row.get("WorkoutRole", "").strip(),
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
    equipmentAccess: Optional[List[str]] = Field(default_factory=list)
    location: Optional[str] = Field(default=None)
    archetype: Optional[str] = Field(default=None)
    userPrefs: Optional[List[str]] = Field(default_factory=list)
    injuries: Optional[List[str]] = Field(default_factory=list)
    focus: Optional[str] = Field(default="Full Body")
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

def determine_equipment(location: str, user_equipment: List[str]) -> List[str]:
    if user_equipment:
        return user_equipment
    if location == "Gym":
        return ["Barbell", "Dumbbells", "Cable", "Machine", "Kettlebell", "Bodyweight"]
    if location == "Home":
        return ["Bodyweight", "Dumbbells", "Bands"]
    if location == "Studio":
        return ["Bodyweight", "Yoga Mat", "Boxing Bag", "Bands"]
    return ["Bodyweight"]

@app.post("/generate-workout", response_model=List[ExerciseOut])
def generate_workout(data: WorkoutRequest):
    if not data.archetype:
        raise HTTPException(status_code=400, detail="Archetype is required.")

    data.equipmentAccess = determine_equipment(data.location, data.equipmentAccess)
    time_budget = data.availableTime
    suggestions = check_for_static_weights(user_logs)
    workout = []

    # --- Step 1: Main Compound ---
    main_pool = [
        ex for ex in EXERCISES
        if ex["workoutRole"] == "MainCompound"
        and data.archetype in ex["archetypes"]
        and any(eq in data.equipmentAccess for eq in ex["equipment"])
        and not any(pref.lower() in ex["name"].lower() for pref in data.userPrefs)
        and (data.focus == "Full Body" or ex["bodyRegion"] == data.focus)
    ]

    if not main_pool:
        raise HTTPException(status_code=404, detail="No main compound exercises found.")

    main_lift = random.choice(main_pool)
    workout.append(main_lift)
    time_budget -= 10

    # --- Step 2: Fill with Remaining Exercises ---
    accessory_pool = [
        ex for ex in EXERCISES
        if ex["name"] != main_lift["name"]
        and data.archetype in ex["archetypes"]
        and any(eq in data.equipmentAccess for eq in ex["equipment"])
        and not any(pref.lower() in ex["name"].lower() for pref in data.userPrefs)
        and (data.focus == "Full Body" or ex["bodyRegion"] == data.focus)
    ]

    num_blocks = max(1, time_budget // 10)
    selected = random.sample(accessory_pool, min(num_blocks, len(accessory_pool)))
    workout.extend(selected)

    # --- Step 3: Format ---
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
