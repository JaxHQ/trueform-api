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

# Sentinel Mobility CSV
MOBILITY_CSV = "https://docs.google.com/spreadsheets/d/e/2PACX-1vTJq8tvNY3AwbGsEKqP0UDhoK6WCBcQfo320JREqMfBiaUtYzRuu2t1oqkNsoR6vpQX-26NknHa7W1H/pub?output=csv"

MOBILITY_BLOCKS = []
try:
    df_mob = pd.read_csv(MOBILITY_CSV)
    df_mob = df_mob[df_mob['Exercise Name'].notna()]
    for _, row in df_mob.iterrows():
        MOBILITY_BLOCKS.append({
            "name": str(row["Exercise Name"]).strip(),
            "blockType": str(row["Type"]).strip(),  # e.g. MobilityFlow or StretchHold
            "workDuration": str(row.get("Work Duration", "30s")),
            "restDuration": str(row.get("Rest Duration", "15s")),
            "suggestedRounds": int(row.get("Suggested Rounds", 1)),
            "isTimed": str(row.get("Is Timed", "TRUE")).lower() == "true",
            "intensityRange": str(row.get("Intensity Range", "Low")),
            "trainingPurpose": str(row.get("Training Purpose", "")).strip(),
            "archetype": "Sentinel"
        })
except Exception as e:
    print("❌ Failed to load mobility exercises:", e)

class MobilityRequest(BaseModel):
    duration: int  # 10, 20, 30
    archetype: str = "Sentinel"

class MobilityBlock(BaseModel):
    name: str
    blockType: str
    workDuration: str
    restDuration: str
    suggestedRounds: int
    isTimed: bool
    intensityRange: str
    trainingPurpose: str
    archetype: str

@app.post("/generate-mobility", response_model=List[MobilityBlock])
def generate_mobility(data: MobilityRequest):
    archetype = data.archetype
    duration = data.duration

    if archetype != "Sentinel":
        raise HTTPException(status_code=400, detail="Only 'Sentinel' supported for now.")

    # Basic logic: return enough blocks to fill duration (estimate each block is ~2 min)
    time_per_block = 2
    num_blocks = min(len(MOBILITY_BLOCKS), duration // time_per_block)
    if num_blocks == 0:
        raise HTTPException(status_code=404, detail="Not enough time for a session.")

    selected = random.sample(MOBILITY_BLOCKS, num_blocks)

    return selected   

# this is weight training csv
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
    availableTime: int
    archetype: str
    focus: str

    daysPerWeek: Optional[int] = None
    lastWorked: Optional[Dict[str, int]] = None
    weeklyVolume: Optional[Dict[str, int]] = None
    equipmentAccess: Optional[List[str]] = Field(default_factory=list)
    userPrefs: Optional[List[str]] = Field(default_factory=list)
    goal: Optional[str] = None

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

# Load Conditioning Exercises
CONDITIONING_CSV = "https://docs.google.com/spreadsheets/d/e/2PACX-1vQjruXErFS6DomownUiQwpOpG_bRGoFTIkzv0uj8fI6dPKh6-nt3KBZ69XdHVqj_lfUFkNTX7FSQkIN/pub?output=csv"

CONDITIONING_EXERCISES = []
try:
    df_cond = pd.read_csv(CONDITIONING_CSV)
    df_cond = df_cond[df_cond['Exercise Name'].notna()]
    for _, row in df_cond.iterrows():
        CONDITIONING_EXERCISES.append({
            "name": str(row["Exercise Name"]).strip(),
            "workoutSubtype": str(row["Workout Subtype"]).strip().lower(),
            "archetypes": [a.strip() for a in str(row["Archetype Tags"]).split(",") if a.strip()],
            "equipment": [e.strip() for e in str(row["Equipment Used"]).split(",") if e.strip()],
            "workDuration": str(row.get("Work Duration", "30s")),
            "restDuration": str(row.get("Rest Duration", "30s")),
            "suggestedRounds": int(row.get("Suggested Rounds", 3)),
            "isTimed": str(row.get("Is Timed", "TRUE")).lower() == "true",
            "intensityRange": str(row.get("Intensity Range", "Moderate")),
        })
except Exception as e:
    print("❌ Failed to load conditioning exercise list:", e)

# Conditioning Block Plan
CONDITIONING_BLOCKS = {
    "Igniter": {
        15: [("sprintblock", 1), ("hiitfinish", 1)],
        30: [("sprintblock", 1), ("explosivecircuit", 1), ("hiitfinish", 1)],
        45: [("sprintblock", 2), ("explosivecircuit", 2), ("hiitfinish", 1)],
    },
    "Engine": {
        15: [("zone2block", 1)],
        30: [("zone2block", 1), ("tempoblock", 1)],
        45: [("zone2block", 1), ("tempoblock", 1)],
        60: [("zone2block", 1), ("tempoblock", 1)],
    }
}

class ConditioningRequest(BaseModel):
    archetype: str  # "Igniter" or "Engine"
    duration: int  # 15, 30, 45, or 60
    equipmentAccess: Optional[List[str]] = Field(default_factory=list)

class ConditioningBlock(BaseModel):
    name: str
    blockType: str
    workDuration: str
    restDuration: str
    suggestedRounds: int
    isTimed: bool
    intensityRange: str
    equipment: List[str]
    archetype: str

@app.post("/generate-conditioning", response_model=List[ConditioningBlock])
def generate_conditioning(data: ConditioningRequest):
    archetype = data.archetype
    duration = data.duration
    equipment = data.equipmentAccess or [
    "AirBike", "Treadmill", "Rowing Machine", "Jump Rope", "Battle Ropes", 
    "Spin Bike", "StepMill", "Weighted Vest", "Bodyweight", "Kettlebell", "Medicine Ball"
]

    if archetype not in CONDITIONING_BLOCKS:
        raise HTTPException(status_code=400, detail="Invalid conditioning archetype.")

    time_plan = CONDITIONING_BLOCKS[archetype].get(duration)
    if not time_plan:
        raise HTTPException(status_code=400, detail="Invalid time selection for archetype.")

    output = []

    for subtype, count in time_plan:
        matching = [
            ex for ex in CONDITIONING_EXERCISES
            if (
                ex["workoutSubtype"].strip().lower() == subtype
                and archetype in ex["archetypes"]
                and any(eq in equipment for eq in ex["equipment"])
            )
        ]

        if not matching:
            print(f"⚠️ No conditioning exercises found for: {subtype}")
            continue

        selected = random.sample(matching, min(count, len(matching)))
        for ex in selected:
            output.append({
                "name": ex["name"],
                "blockType": ex["workoutSubtype"],
                "workDuration": ex["workDuration"],
                "restDuration": ex["restDuration"],
                "suggestedRounds": ex["suggestedRounds"],
                "isTimed": ex["isTimed"],
                "intensityRange": ex["intensityRange"],
                "equipment": ex["equipment"],
                "archetype": archetype
            })

    if not output:
        raise HTTPException(status_code=404, detail="No matching conditioning blocks found.")

    return output
