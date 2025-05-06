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

# --- Load Local Cleaned CSV ---
CSV_PATH = "Cleaned_Exercise_List.csv"

EXERCISES = []
try:
    df = pd.read_csv(CSV_PATH)
    for _, row in df.iterrows():
        EXERCISES.append({
            "name": row.get("Exercise Name", "").strip(),
            "muscleGroup": row.get("Primary Muscle Group", "").strip(),
            "bodyRegion": row.get("Body Region", "").strip().lower(),
            "movementType": row.get("Movement Type", "").strip(),
            "equipment": [e.strip() for e in str(row.get("Equipment Used", "")).split(",")],
            "workoutRole": row.get("Workout Role", "").strip().lower(),
            "workoutSubtype": row.get("Workout Subtype", "").strip().lower(),
            "archetype": row.get("Archetype Tags", "").strip(),  # now single value only
        })
except Exception as e:
    print("❌ Failed to load exercise list:", e)

REST_TIME_DEFAULT = 60

# --- Archetype Plan Logic ---
ARCHETYPE_PLANS = {
    "Titan": [
        ("PowerCompound", 4, "5"),
        ("VolumeCompound", 4, "6"),
        ("BilateralIsolation", 3, "10-12"),
        ("BilateralIsolation", 3, "10-12"),
        ("Core", 3, "15"),
    ],
    "Apex": [
        ("PowerCompound", 3, "3-5"),
        ("VolumeCompound", 3, "6-8"),
        ("UnilateralIsolation", 3, "10"),
        ("BilateralIsolation", 3, "10-12"),
        ("Core", 3, "20"),
    ],
    "Vanguard": [
        ("Offset Load", 3, "6-8"),
        ("UnilateralCompound", 3, "8"),
        ("Isometric", 3, "20-30s"),
        ("Carry/Load", 3, "30s"),
        ("Core", 3, "15"),
    ],
    "Prime": [
        ("PowerCompound", 3, "3-5"),
        ("Explosive", 3, "5"),
        ("Contrast Set", 3, "6"),
        ("UnilateralIsolation", 2, "8-10"),
        ("Core", 3, "20"),
    ],
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
    if not data.archetype:
        raise HTTPException(status_code=400, detail="Archetype is required.")

    # Equipment fallback logic
    if data.location == "Home":
        data.equipmentAccess = ["Bodyweight"]
    elif not data.equipmentAccess:
        data.equipmentAccess = ["Barbell", "Dumbbell", "Cable", "Kettlebell", "Machine", "Bodyweight"]

    plan = ARCHETYPE_PLANS.get(data.archetype)
    if not plan:
        raise HTTPException(status_code=400, detail="No plan for archetype.")

    output = []

    for subtype, sets, reps in plan:
        filtered = [
            ex for ex in EXERCISES
            if ex["archetype"] == data.archetype
            and (
                ex["workoutSubtype"] == subtype.lower()
                or ex["workoutRole"] == subtype.lower()
            )
            and any(eq in data.equipmentAccess for eq in ex["equipment"])
            and (
                data.focus.lower() == "full body"
                or ex["bodyRegion"] == data.focus.lower()
            )
            and not any(pref.lower() in ex["name"].lower() for pref in data.userPrefs)
        ]

        if not filtered:
            print(f"⚠️ No exercises found for subtype '{subtype}' and archetype '{data.archetype}'")
            continue

        chosen = random.choice(filtered)
        alts = [
            alt["name"] for alt in filtered
            if alt["name"] != chosen["name"]
            and alt["muscleGroup"] == chosen["muscleGroup"]
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

    return output