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

# Load CSV from Google Sheets URL
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
            "equipment": [e.strip() for e in str(row["Equipment Used"]).split(",") if e.strip()],
            "workoutRole": str(row["Workout Role"]).strip().lower(),
            "workoutSubtype": str(row["Workout Subtype"]).strip().lower(),
            "archetypes": [a.strip() for a in str(row["Archetype Tags"]).split(",") if a.strip()],
        })
except Exception as e:
    print("❌ Failed to load exercise list:", e)

REST_TIME_DEFAULT = 60

ARCHETYPE_PLANS = {
    "Prime": [
        ("powercompound", 3, "3-5"),  # Main lift
        ("explosive", 3, "5"),
        ("contrast set", 3, "6"),
        ("unilateralisolation", 2, "8-10"),
        ("core", 3, "20"),  # Core last
    ],
    "Titan": [
        ("powercompound", 4, "5"),  # Main lift
        ("volumecompound", 4, "6"),
        ("bilateralisolation", 3, "10-12"),
        ("bilateralisolation", 3, "10-12"),
        ("core", 3, "15"),  # Core last
    ],
    "Vanguard": [
        ("offset load", 3, "6-8"),  # Main lift
        ("unilateralcompound", 3, "8"),
        ("isometric", 3, "20-30s"),
        ("carry/load", 3, "30s"),
        ("core", 3, "15"),  # Core last
    ],
    "Bodyweight": [
        ("mobility", 2, "30-60s"),  # Main lift (mobility to start)
        ("explosive", 2, "5-6"),
        ("lowercompound", 2, "10-15"),
        ("uppercompound", 2, "8-12"),
        ("unilateral", 2, "8-10"),
        ("isometric", 2, "20-30s"),
        ("core", 2, "20"),  # Core last
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
    "mobility": 5,
    "lowercompound": 6,
    "uppercompound": 6,
    "unilateral": 6,
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
    focus: Optional[str] = Field(default="Full Body")  # Upper, Lower, or Full Body

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

    # Normalize focus to lowercase and validate
    focus = data.focus.lower().replace(" ", "")  # Remove spaces for "Full Body"
    focus_map = {
        "upper": "upper",
        "upperbody": "upper",
        "lower": "lower",
        "lowerbody": "lower",
        "fullbody": "full body",
        "full": "full body"
    }
    if focus not in focus_map:
        raise HTTPException(status_code=400, detail="Focus must be Upper, Lower, or Full Body")
    focus = focus_map[focus]  # Map to internal lowercase format

    output = []
    current_time = 0
    max_time = data.availableTime

    # Ensure main lift (first in plan) and core (last in plan) are included
    main_lift = plan[0]  # First exercise is the main lift
    core_exercise = plan[-1]  # Last exercise is core
    remaining_plan = plan[1:-1]  # Middle exercises to fill time

    # Helper function to filter exercises
    def filter_exercises(subtype, sets, reps):
        subtype_clean = subtype.strip().lower()
        block_time = SUBTYPE_TIMES.get(subtype_clean, 6)

        # Adjust body region based on focus, but allow core for core subtype
        if subtype_clean == "core":
            body_region_filter = ["core"]  # Only core exercises for core subtype
        else:
            body_region_filter = (
                ["upper"] if focus == "upper" else
                ["lower"] if focus == "lower" else
                ["upper", "lower", "full body", "core"]
            )

        filtered = [
            ex for ex in EXERCISES
            if (
                (subtype_clean == ex["workoutSubtype"].strip().lower() or
                 subtype_clean == ex["workoutRole"].strip().lower())
                and (
                    data.archetype == "Bodyweight" and "BodyWeight" in ex["archetypes"] or
                    data.archetype in ex["archetypes"]
                )
                and any(eq in data.equipmentAccess for eq in ex["equipment"])
                and ex["bodyRegion"] in body_region_filter
                and not any(pref.lower() in ex["name"].lower() for pref in data.userPrefs)
            )
        ]

        return filtered, block_time

    # Add main lift
    filtered, block_time = filter_exercises(*main_lift)
    if filtered and current_time + block_time <= max_time:
        chosen = random.choice(filtered)
        alts = [
            alt["name"] for alt in filtered
            if alt["name"] != chosen["name"] and alt["muscleGroup"] == chosen["muscleGroup"]
        ]
        output.append({
            "name": chosen["name"],
            "muscleGroup": chosen["muscleGroup"],
            "movementType": chosen["movementType"],
            "sets": main_lift[1],
            "reps": main_lift[2],
            "rest": REST_TIME_DEFAULT,
            "alternatives": random.sample(alts, min(3, len(alts))),
            "suggestion": "Main lift to start the workout"
        })
        current_time += block_time

    # Add middle exercises based on available time
    for subtype, sets, reps in remaining_plan:
        if current_time + SUBTYPE_TIMES.get(subtype.lower(), 6) > max_time - SUBTYPE_TIMES.get("core", 5):
            break  # Reserve time for core

        filtered, block_time = filter_exercises(subtype, sets, reps)
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

    # Add core exercise
    filtered, block_time = filter_exercises(*core_exercise)
    if filtered and current_time + block_time <= max_time:
        chosen = random.choice(filtered)
        alts = [
            alt["name"] for alt in filtered
            if alt["name"] != chosen["name"] and alt["muscleGroup"] == chosen["muscleGroup"]
        ]
        output.append({
            "name": chosen["name"],
            "muscleGroup": chosen["muscleGroup"],
            "movementType": chosen["movementType"],
            "sets": core_exercise[1],
            "reps": core_exercise[2],
            "rest": REST_TIME_DEFAULT,
            "alternatives": random.sample(alts, min(3, len(alts))),
            "suggestion": "Core exercise to finish the workout"
        })

    if not output:
        raise HTTPException(status_code=400, detail="No exercises found matching criteria")

    return output