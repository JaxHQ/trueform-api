from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Any
import random
import pandas as pd

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Load Exercise List from Google Sheets ---
CSV_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vQ04XU88PE6x8GET2SblG-f7Gx-XWTvClQqm5QOdQ_EE682yDqMHY25EcR3N7qjIwa5lM_S_azLaM6n/pub?gid=1956029134&single=true&output=csv"
EXERCISES = []

try:
    df = pd.read_csv(CSV_URL)
    for _, row in df.iterrows():
        EXERCISES.append({
            "name": row.get("Exercise Name", "").strip(),
            "muscleGroup": row.get("Primary Muscle Group", "").strip(),
            "movementType": row.get("Movement Type", "").strip(),
            "workoutRole": row.get("WorkoutRole", "").strip(),
            "equipment": [e.strip() for e in str(row.get("Equipment Used", "")).split(",")],
            "archetypes": [a.strip() for a in str(row.get("Archetype Tags", "")).split(",")],
            "bodyRegion": row.get("Body Region", "").strip(),
        })
    print(f"✅ Loaded {len(EXERCISES)} exercises.")
except Exception as e:
    print("❌ Failed to load exercises:", e)

# --- Archetype-Based Workout Templates ---
ARCHETYPE_TEMPLATES = {
    "Titan": [
        ("MainCompound", 4, "6"),
        ("MainCompound", 4, "6"),
        ("Isolation", 3, "10-12"),
        ("Isolation", 3, "10-12"),
        ("Core", 3, "15"),
    ],
    "Apex": [
        ("PowerCompound", 3, "3-5"),
        ("MainCompound", 3, "6-8"),
        ("Isolation", 3, "10"),
        ("Isolation", 3, "10-12"),
        ("Core", 3, "20"),
    ],
    "Vanguard": [
        ("MainCompound", 4, "6-8"),
        ("Isolation", 3, "10-12"),
        ("Core", 3, "15"),
    ],
    "Prime": [
        ("MainCompound", 3, "5-8"),
        ("Isolation", 3, "8-10"),
        ("Core", 3, "15-20"),
    ]
}

# --- Models ---
class WorkoutRequest(BaseModel):
    availableTime: int
    equipmentAccess: Optional[List[str]] = Field(default_factory=list)
    location: Optional[str] = Field(default=None)
    archetype: Optional[str] = Field(default=None)
    userPrefs: Optional[List[str]] = Field(default_factory=list)
    focus: Optional[str] = Field(default="Full Body")

class ExerciseOut(BaseModel):
    name: str
    muscleGroup: str
    movementType: str
    sets: int
    reps: str
    rest: int
    alternatives: List[str]

# --- Utility ---
def get_equipment(location: str) -> List[str]:
    if location == "Home":
        return ["Bodyweight"]
    if location == "Gym":
        return ["Barbell", "Dumbbells", "Cable", "Machine", "Kettlebell", "Bodyweight"]
    return ["Bodyweight"]

# --- Workout Generator ---
@app.post("/generate-workout", response_model=List[ExerciseOut])
def generate_workout(data: WorkoutRequest):
    if not data.archetype or data.archetype not in ARCHETYPE_TEMPLATES:
        raise HTTPException(status_code=400, detail="Archetype required or not supported.")
    
    equipment = get_equipment(data.location)
    template = ARCHETYPE_TEMPLATES[data.archetype]
    output = []

    for role, sets, reps in template:
        filtered = [
            ex for ex in EXERCISES
            if role.lower() == ex["workoutRole"].strip().lower()
            and data.archetype in ex["archetypes"]
            and (data.focus == "Full Body" or ex["bodyRegion"] == data.focus)
            and any(eq in equipment for eq in ex["equipment"])
            and not any(pref.lower() in ex["name"].lower() for pref in data.userPrefs)
        ]

        if not filtered:
            continue

        chosen = random.choice(filtered)
        alts = [
            alt["name"] for alt in filtered
            if alt["name"] != chosen["name"]
            and alt["muscleGroup"] == chosen["muscleGroup"]
            and alt["movementType"] == chosen["movementType"]
        ]

        output.append({
            "name": chosen["name"],
            "muscleGroup": chosen["muscleGroup"],
            "movementType": chosen["movementType"],
            "sets": sets,
            "reps": reps,
            "rest": 60,
            "alternatives": random.sample(alts, min(3, len(alts)))
        })

    return output
