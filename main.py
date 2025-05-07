from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Dict, Optional
import random
import pandas as pd

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

CSV_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vQ04XU88PE6x8GET2SblG-f7Gx-XWTvClQqm5QOdQ_EE682yDqMHY25EcR3N7qjIwa5lM_S_azLaM6n/pub?output=csv"

EXERCISES = []

try:
    df = pd.read_csv(CSV_URL)
    df = df[df['Exercise Name'].notna()]  # Skip rows without exercise name
    for _, row in df.iterrows():
        EXERCISES.append({
            "name": str(row["Exercise Name"]).strip(),
            "muscleGroup": str(row["Primary Muscle Group"]).strip(),
            "bodyRegion": str(row["Body Region"]).strip().lower(),
            "movementType": str(row["Movement Type"]).strip(),
            "equipment": [e.strip() for e in str(row["Equipment Used"]).split(",")],
            "workoutRole": str(row["Workout Role"]).strip().lower(),
            "workoutSubtype": str(row["Workout Subtype"]).strip().lower(),
            "archetypes": [a.strip() for a in str(row["Archetype Tags"]).split(",") if a.strip()],
        })
except Exception as e:
    print("❌ Failed to load exercise list:", e)

REST_TIME_DEFAULT = 60

ARCHETYPE_PLANS = {
    "Apex": [
        ("powercompound", 3, "3-5"),
        ("volumecompound", 3, "6-8"),
        ("unilateralisolation", 3, "10"),
        ("bilateralisolation", 3, "10-12"),
        ("core", 3, "20"),
    ],
    "Prime": [
        ("powercompound", 3, "3-5"),
        ("explosive", 3, "5"),
        ("contrast set", 3, "6"),
        ("unilateralisolation", 2, "8-10"),
        ("core", 3, "20"),
    ],
    "Titan": [
        ("powercompound", 4, "5"),
        ("volumecompound", 4, "6"),
        ("bilateralisolation", 3, "10-12"),
        ("bilateralisolation", 3, "10-12"),
        ("core", 3, "15"),
    ],
    "Vanguard": [
        ("offset load", 3, "6-8"),
        ("unilateralcompound", 3, "8"),
        ("isometric", 3, "20-30s"),
        ("carry/load", 3, "30s"),
        ("core", 3, "15"),
    ],
    "Bodyweight": [
        ("free", 3, "10-15"),
        ("free", 3, "10-15"),
        ("free", 3, "10-15"),
        ("free", 3, "10-15"),
        ("core", 3, "20"),
    ]
}

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
    "free": 6,
}

class WorkoutRequest(BaseModel):
    daysPerWeek: int
    availableTime: int
    lastWorked: Dict[str, int]
    weeklyVolume: Dict[str, int]
    equipmentAccess: Optional[List[str]] = Field(default_factory=list)
    location: Optional[str] = None
    archetype: str
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
    suggestion: Optional[str] = None

@app.post("/generate-workout", response_model=List[ExerciseOut])
def generate_workout(data: WorkoutRequest):
    if not data.archetype:
        raise HTTPException(status_code=400, detail="Archetype is required.")

    if data.archetype == "Bodyweight":
        data.equipmentAccess = ["Bodyweight"]
    elif not data.equipmentAccess:
        data.equipmentAccess = ["Barbell", "Dumbbell", "Cable", "Kettlebell", "Machine", "Bodyweight"]

    plan = ARCHETYPE_PLANS.get(data.archetype)
    if not plan:
        raise HTTPException(status_code=400, detail="Invalid archetype")

    output = []
    current_time = 0
    max_time = data.availableTime

    for idx, (subtype, sets, reps) in enumerate(plan):
        subtype_clean = subtype.strip().lower()
        block_time = SUBTYPE_TIMES.get(subtype_clean, 6)

        if current_time + block_time > max_time:
            break

        filtered = [
            ex for ex in EXERCISES
            if (
                subtype_clean == "free"
                or subtype_clean == ex["workoutSubtype"].strip().lower()
                or subtype_clean == ex["workoutRole"].strip().lower()
            )
            and (data.archetype in ex["archetypes"] or data.archetype == "Bodyweight")
            and any(eq in data.equipmentAccess for eq in ex["equipment"])
            and (subtype_clean == "core" or ex["bodyRegion"] != "core")
            and not any(pref.lower() in ex["name"].lower() for pref in data.userPrefs)
        ]

        if not filtered:
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
