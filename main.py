from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Optional, Any
import random
import pandas as pd
from datetime import datetime

app = FastAPI()

# ------------------------- CORS -------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ------------------------- Data Load -------------------------
CSV_PATH = "Cleaned_Master_Exercise_List.csv"
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

print(f"✅ Loaded {len(EXERCISES)} exercises.")

# ------------------------- Constants -------------------------
REST_TIME_DEFAULT = 60
user_logs = {}

# ------------------------- Models -------------------------

class WorkoutRequest(BaseModel):
    daysPerWeek: int
    availableTime: int
    lastWorked: Dict[str, int]
    weeklyVolume: Dict[str, int]
    equipmentAccess: List[str]
    archetype: Optional[str] = None
    userPrefs: Optional[List[str]] = []
    injuries: Optional[List[str]] = []
    goal: Optional[str] = None  # made optional

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

# ------------------------- Helpers -------------------------

def check_for_static_weights(logs: dict):
    suggestions = {}
    for exercise_id, entries in logs.items():
        if len(entries) < 3:
            continue
        last_3_weights = [tuple(entry["weights"]) for entry in entries[-3:]]
        if all(w == last_3_weights[0] for w in last_3_weights):
            suggestions[exercise_id] = (
                "You've used the same weight 3 sessions in a row. Try increasing slightly if it feels too easy."
            )
    return suggestions

# ------------------------- Endpoints -------------------------

@app.post("/generate-workout", response_model=List[ExerciseOut])
def generate_workout(data: WorkoutRequest):
    if not data.archetype:
        raise HTTPException(status_code=400, detail="Archetype is required.")

    # Filter exercises
    matching_exercises = [
        ex for ex in EXERCISES
        if data.archetype in ex["archetypes"]
        and any(eq in data.equipmentAccess for eq in ex["equipment"])
        and not any(pref.lower() in ex["name"].lower() for pref in data.userPrefs)
    ]

    if not matching_exercises:
        raise HTTPException(status_code=404, detail="No exercises found for that archetype and equipment.")

    # Limit to appropriate workout length
    num_blocks = max(1, data.availableTime // 10)
    selected = random.sample(matching_exercises, min(num_blocks, len(matching_exercises)))
    suggestions = check_for_static_weights(user_logs)

    # Format output
    output = []
    for ex in selected:
        ex_id = ex["name"].lower().replace(" ", "-")
        alts = [
            alt["name"] for alt in matching_exercises
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

@app.post("/log-workout")
def log_workout(log: WorkoutLog):
    for ex in log.exercises:
        ex_id = ex["name"].lower().replace(" ", "-")
        if ex_id not in user_logs:
            user_logs[ex_id] = []
        entry = {"date": log.date, "weights": ex.get("weights", [])}
        user_logs[ex_id].append(entry)
    return {"message": "Workout logged successfully."}

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
        and any(eq in equipment for eq in ex["equipment"])
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