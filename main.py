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
    goal: Optional[str] = None
    prepType: Optional[str] = "Skip"  # "Warm-Up", "Conditioning", "Both", "Skip"

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

    prep_blocks = 0
    if data.prepType == "Warm-Up" or data.prepType == "Conditioning":
        prep_blocks = 1
    elif data.prepType == "Both":
        prep_blocks = 2

    total_blocks = max(1, data.availableTime // 10)
    main_blocks = max(1, total_blocks - prep_blocks)

    suggestions = check_for_static_weights(user_logs)

    # Filter functions
    def matches(ex, tag):
        return (
            tag in ex["archetypes"]
            and any(eq in data.equipmentAccess for eq in ex["equipment"])
            and not any(pref.lower() in ex["name"].lower() for pref in data.userPrefs)
        )

    main_pool = [ex for ex in EXERCISES if matches(ex, data.archetype)]
    warmup_pool = [ex for ex in EXERCISES if "Warm-Up" in ex["otherTags"] and matches(ex, data.archetype)]
    conditioning_pool = [ex for ex in EXERCISES if "Conditioning" in ex["otherTags"] and matches(ex, data.archetype)]

    if not main_pool:
        raise HTTPException(status_code=404, detail="No exercises found for archetype and equipment.")

    workout = []

    # Optional warm-up first
    if data.prepType in ["Warm-Up", "Both"] and warmup_pool:
        warm = random.choice(warmup_pool)
        workout.append(format_exercise(warm, main_pool, suggestions))

    # Main workout
    for ex in random.sample(main_pool, min(main_blocks, len(main_pool))):
        workout.append(format_exercise(ex, main_pool, suggestions))

    # Optional conditioning last
    if data.prepType in ["Conditioning", "Both"] and conditioning_pool:
        cond = random.choice(conditioning_pool)
        workout.append(format_exercise(cond, conditioning_pool, suggestions))

    return workout


def format_exercise(ex, pool, suggestions):
    ex_id = ex["name"].lower().replace(" ", "-")
    alts = [
        alt["name"] for alt in pool
        if alt["name"] != ex["name"]
        and alt["muscleGroup"] == ex["muscleGroup"]
        and alt["movementType"] == ex["movementType"]
    ]
    return {
        "name": ex["name"],
        "muscleGroup": ex["muscleGroup"],
        "movementType": ex["movementType"],
        "sets": 4,
        "reps": "8-12",
        "rest": REST_TIME_DEFAULT,
        "alternatives": random.sample(alts, min(3, len(alts))),
        "suggestion": suggestions.get(ex_id)
    }

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

    return format_exercise(random.choice(pool), pool, {})
