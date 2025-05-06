from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Dict, Optional
import random
import pandas as pd

app = FastAPI()

# --- CORS Setup ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Load Exercises from Google Sheets ---
CSV_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vQ04XU88PE6x8GET2SblG-f7Gx-XWTvClQqm5QOdQ_EE682yDqMHY25EcR3N7qjIwa5lM_S_azLaM6n/pub?output=csv"

EXERCISES = []

try:
    df = pd.read_csv(CSV_URL)
    for _, row in df.iterrows():
        EXERCISES.append({
            "name": str(row.get("Exercise Name", "")).strip(),
            "muscleGroup": str(row.get("Primary Muscle Group", "")).strip(),
            "bodyRegion": str(row.get("Body Region", "")).strip().lower(),
            "movementType": str(row.get("Movement Type", "")).strip(),
            "equipment": [e.strip() for e in str(row.get("Equipment Used", "")).split(",")],
            "workoutRole": str(row.get("Workout Role", "")).strip().lower(),
            "workoutSubtype": str(row.get("Workout Subtype", "")).strip().lower(),
            "archetypes": [a.strip() for a in str(row.get("Archetype Tags", "")).split(",") if a.strip()],
        })
except Exception as e:
    print("❌ Failed to load exercise list:", e)

REST_TIME_DEFAULT = 60

# Simplified fallback plan for now
FALLBACK_PLAN = [
    ("PowerCompound", 4, "5"),
    ("VolumeCompound", 4, "6"),
    ("VolumeCompound", 3, "8-10"),
    ("Core", 3, "15"),
    ("Core", 3, "20"),
]

SUBTYPE_TIMES = {
    "powercompound": 10,
    "volumecompound": 8,
    "unilateralisolation": 6,
    "bilateralisolation": 6,
    "core": 5,
    "explosive": 6,
    "contrast set": 8,
    "carry/load": 6,
    "offset load": 6,
    "isometric": 5,
    "unilateralcompound": 6,
}

REGION_MAP = {
    "upper": "upper body",
    "lower": "lower body",
    "full body": "full body",
    "core": "core"
}

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

@app.post("/generate-workout", response_model=List[ExerciseOut])
def generate_workout(data: WorkoutRequest):
    # Equipment setup
    if data.location == "Home":
        data.equipmentAccess = ["Bodyweight"]
    elif not data.equipmentAccess:
        data.equipmentAccess = ["Barbell", "Dumbbell", "Cable", "Kettlebell", "Machine", "Bodyweight"]

    plan = FALLBACK_PLAN

    output = []
    current_time = 0
    max_time = data.availableTime
    focus_clean = data.focus.strip().lower()

    for subtype, sets, reps in plan:
        subtype_clean = subtype.strip().lower()
        block_time = SUBTYPE_TIMES.get(subtype_clean, 6)

        if current_time + block_time > max_time:
            print(f"⏭ Skipping {subtype_clean} — not enough time.")
            continue

        filtered = [
            ex for ex in EXERCISES
            if (
                subtype_clean == ex.get("workoutSubtype", "").strip().lower()
                or subtype_clean == ex.get("workoutRole", "").strip().lower()
            )
            and any(eq in data.equipmentAccess for eq in ex["equipment"])
            and (
                focus_clean == "full body"
                or ex["workoutSubtype"] == "core"
                or REGION_MAP.get(ex["bodyRegion"].strip().lower()) == focus_clean
            )
            and not any(pref.lower() in ex["name"].lower() for pref in data.userPrefs)
        ]

        if not filtered:
            print(f"⚠️ No exercises found for subtype '{subtype}'")
            continue

        chosen = random.choice(filtered)
        alts = [
            alt["name"] for alt in filtered
            if alt["name"] != chosen["name"] and alt["muscleGroup"] == chosen["muscleGroup"]
        ]

        output.append({
            "name": chosen["name"],
            "muscleGroup": chosen["muscleGroup"],
            "movementType": chosen["movementType"],
            "sets": sets,
            "reps": reps,
            "rest": REST_TIME_DEFAULT,
            "alternatives": random.sample(alts, min(3, len(alts))),
            "suggestion": None
        })

        current_time += block_time

    return output
