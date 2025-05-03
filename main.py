from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Optional, Any
import random
import pandas as pd
from datetime import datetime

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

MIN_REST_DAYS = 1
CURRENT_DAY = 7

GOAL_VOLUME_MAP = {
    "strength": 10,
    "aesthetics": 15,
    "performance": 12,
    "longevity": 10
}

REST_TIME_MAP = {
    "strength": 120,
    "aesthetics": 60,
    "performance": 75,
    "longevity": 60,
    "conditioning": 30
}

CSV_PATH = "Cleaned_Master_Exercise_List.csv"
df = pd.read_csv(CSV_PATH)

EXERCISES = []
for _, row in df.iterrows():
    EXERCISES.append({
        "name": row["Exercise Name"],
        "muscleGroup": row["Muscle Group"],
        "movementType": row["Movement Type"],
        "equipment": [e.strip() for e in str(row["Equipment"]).split(",") if e],
        "archetypes": [a.strip() for a in str(row["Archetype Tags"]).split(",") if a],
        "otherTags": [t.strip() for t in str(row["Other Tags"]).split(",") if t]
    })

print(f"✅ Loaded {len(EXERCISES)} exercises")

class WorkoutRequest(BaseModel):
    daysPerWeek: int
    availableTime: int
    goal: str
    lastWorked: Dict[str, int]
    weeklyVolume: Dict[str, int]
    equipmentAccess: List[str]
    archetype: Optional[str] = None
    userPrefs: Optional[List[str]] = []
    injuries: Optional[List[str]] = []

class ExerciseOut(BaseModel):
    name: str
    muscleGroup: str
    movementType: str
    sets: int
    reps: str
    rest: Optional[int] = 60
    alternatives: List[str]
    suggestion: Optional[str] = None

@app.post("/generate-workout", response_model=List[ExerciseOut])
def generate_workout(data: WorkoutRequest):
    target_sets = GOAL_VOLUME_MAP.get(data.goal.lower(), 12)

    # Step 1: Build muscle score logic with fallback
    muscle_scores = {}

    if data.weeklyVolume:
        for muscle in data.weeklyVolume:
            days_rest = CURRENT_DAY - data.lastWorked.get(muscle, 10)
            volume = data.weeklyVolume.get(muscle, 0)
            muscle_scores[muscle] = max(0, target_sets - volume) if days_rest >= MIN_REST_DAYS else -1
    else:
        # Fallback: balanced split if no history
        default_muscles = ['Chest', 'Back', 'Legs', 'Shoulders', 'Core']
        muscle_scores = {m: 1 for m in default_muscles}

    prioritized_muscles = sorted(
        [m for m, s in muscle_scores.items() if s > 0],
        key=lambda m: muscle_scores[m],
        reverse=True
    )

    selected = []
    for muscle in prioritized_muscles:
        for ex in EXERCISES:
            if ex["muscleGroup"] != muscle:
                continue
            if not any(e in data.equipmentAccess for e in ex["equipment"]):
                continue
            if data.archetype and data.archetype not in ex.get("archetypes", []):
                continue

            alternatives = [alt["name"] for alt in EXERCISES
                if alt["name"] != ex["name"]
                and alt["muscleGroup"] == ex["muscleGroup"]
                and alt["movementType"] == ex["movementType"]
                and any(e in data.equipmentAccess for e in alt["equipment"])
                and (data.archetype is None or data.archetype in alt["archetypes"])
            ]

            selected.append({
                "name": ex["name"],
                "muscleGroup": ex["muscleGroup"],
                "movementType": ex["movementType"],
                "sets": 4,
                "reps": "6-10",
                "rest": REST_TIME_MAP.get(data.goal.lower(), 60),
                "alternatives": random.sample(alternatives, min(3, len(alternatives)))
            })

    limit = min(len(selected), max(1, data.availableTime // 10))
    return random.sample(selected, limit) if selected else []
