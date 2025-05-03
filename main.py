from fastapi import FastAPI, HTTPException, Request
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

CSV_PATH = "TrueForm_Exercise_List_MegaExpanded.csv"
df = pd.read_csv(CSV_PATH)

EXERCISES = []
for _, row in df.iterrows():
    EXERCISES.append({
        "name": row["Exercise Name"],
        "muscleGroup": row["Primary Muscle Group"],
        "movementType": row["Movement Type"],
        "equipment": [e.strip() for e in str(row["Equipment Used"]).split(",")],
        "archetypes": [a.strip() for a in str(row["Archetype Tags"]).split(",")],
        "otherTags": [t.strip() for t in str(row["Other Tags"]).split(",")]
    })

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
    alternatives: List[str]
    suggestion: Optional[str] = None

class WorkoutLog(BaseModel):
    userId: str
    date: str
    exercises: List[Dict[str, Any]]
    duration: int
    goal: str

user_logs = {
    "incline-db-press": [
        {"date": "2025-04-20", "weights": [35, 35, 35, 35]},
        {"date": "2025-04-24", "weights": [35, 35, 35, 35]},
        {"date": "2025-04-28", "weights": [35, 35, 35, 35]}
    ]
}

@app.post("/generate-workout", response_model=List[ExerciseOut])
def generate_workout(data: WorkoutRequest):
    target_sets = GOAL_VOLUME_MAP.get(data.goal.lower(), 12)
    muscle_scores = {}

    for muscle in data.weeklyVolume:
        days_rest = CURRENT_DAY - data.lastWorked.get(muscle, 10)
        volume = data.weeklyVolume.get(muscle, 0)
        muscle_scores[muscle] = max(0, target_sets - volume) if days_rest >= MIN_REST_DAYS else -1

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
            if any(pref.lower() in ex["name"].lower() for pref in data.userPrefs):
                continue
            if data.archetype and data.archetype not in ex.get("archetypes", []):
                continue

            alternatives = [alt["name"] for alt in EXERCISES
                if alt["name"] != ex["name"]
                and alt["muscleGroup"] == ex["muscleGroup"]
                and alt["movementType"] == ex["movementType"]
                and any(e in data.equipmentAccess for e in alt["equipment"])
                and not any(pref.lower() in alt["name"].lower() for pref in data.userPrefs)
                and (data.archetype is None or data.archetype in alt["archetypes"])
            ]

            selected.append({
                "name": ex["name"],
                "muscleGroup": ex["muscleGroup"],
                "movementType": ex["movementType"],
                "sets": 4,
                "reps": "6-10",
                "alternatives": random.sample(alternatives, min(3, len(alternatives)))
            })

    limit = min(len(selected), max(1, data.availableTime // 10))
    suggestions = check_for_static_weights(user_logs)

    for ex in selected:
        ex_id = ex["name"].lower().replace(" ", "-")
        if ex_id in suggestions:
            ex["suggestion"] = suggestions[ex_id]

    return random.sample(selected, limit) if selected else []

@app.post("/log-workout")
def log_workout(log: WorkoutLog):
    print(f"Workout log for user {log.userId} on {log.date}:")
    print(f"- Goal: {log.goal}")
    print(f"- Duration: {log.duration} min")
    for ex in log.exercises:
        print(f"  {ex['name']}: {ex['sets']} sets x {ex['reps']} reps")
    return {"message": "Workout logged successfully."}

def check_for_static_weights(logs: dict):
    suggestions = {}
    for exercise_id, entries in logs.items():
        if len(entries) < 3:
            continue
        last_3_weights = [tuple(entry["weights"]) for entry in entries[-3:]]
        if all(w == last_3_weights[0] for w in last_3_weights):
            suggestions[exercise_id] = (
                "Noticed you've been using the same weight for the last 3 sessions. "
                "If you’re feeling confident, consider slightly increasing the intensity — "
                "even a small bump can make a difference."
            )
    return suggestions