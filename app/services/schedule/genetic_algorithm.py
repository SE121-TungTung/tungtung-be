"""
Genetic Algorithm Schedule Optimizer
=====================================
Pure algorithm module — NO database dependency.
All inputs/outputs use plain dataclasses and dicts.

Architecture:
    - Chromosome = List[Gene]  (one full timetable)
    - Gene = one session assignment (class × day × slots × room)
    - Population = List[Individual]
    - Fitness = -hard_penalty * HARD_WEIGHT + soft_score

Usage:
    result = run_ga(classes, rooms, constraints, config, time_slots_config, date_range)
"""
from __future__ import annotations

import copy
import random
import logging
from dataclasses import dataclass, field
from datetime import date, time, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple
from uuid import UUID

logger = logging.getLogger(__name__)

# ============================================================================
# CONSTANTS
# ============================================================================

HARD_WEIGHT = 1_000  # Ensures any hard violation dominates all soft scores combined

DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

DAY_TO_INDEX = {d: i for i, d in enumerate(DAYS)}

# Time period classification based on slot numbers
TIME_PERIODS: Dict[str, Set[int]] = {
    "morning": {1, 2},
    "afternoon": {3, 4},
    "evening": {5, 6},
}


# ============================================================================
# DATA STRUCTURES — Input
# ============================================================================

@dataclass
class TimeSlotConfig:
    """System time-slot definition (mirrors SYSTEM_TIME_SLOTS in schedule_service)."""
    slot_number: int
    start_time: time
    end_time: time


@dataclass
class GAClassInput:
    """One class that needs sessions scheduled."""
    class_id: UUID
    class_name: str
    teacher_id: UUID
    room_id: Optional[UUID]          # Preferred room (nullable)
    max_students: int
    sessions_per_week: int
    fixed_schedule: List[Dict]       # From Class.schedule JSONB: [{"day": "monday", "slots": [1,2]}, ...]
    preferred_time_period: Optional[str] = None  # "morning" / "afternoon" / "evening"


@dataclass
class GARoomInput:
    """Available room."""
    room_id: UUID
    name: str
    capacity: int


@dataclass
class GAConstraintInput:
    """External constraints fed to the GA engine."""
    # teacher_id → list of (date, blocked_slots).  blocked_slots=[] means whole day.
    teacher_unavailability: Dict[UUID, List[Tuple[date, List[int]]]] = field(default_factory=dict)

    # class_id → list of (day_name, required_slots)
    class_fixed_times: Dict[UUID, List[Tuple[str, List[int]]]] = field(default_factory=dict)

    # Pairs of classes that should be scheduled in the same time period
    paired_classes: List[Tuple[UUID, UUID]] = field(default_factory=list)

    # class_id → exam dates to avoid
    exam_dates: Dict[UUID, List[date]] = field(default_factory=dict)

    # Existing sessions from DB (for "preserve existing" soft constraint)
    # Each dict: {"class_id": UUID, "session_date": date, "time_slots": [int], "room_id": UUID}
    existing_sessions: List[Dict] = field(default_factory=list)


@dataclass
class GAConfig:
    """GA hyperparameters."""
    population_size: int = 100
    generations: int = 300
    crossover_rate: float = 0.70
    mutation_rate: float = 0.15
    elitism_count: int = 5
    tournament_size: int = 5

    # Convergence: stop if best fitness unchanged for this many generations
    convergence_window: int = 30

    # Soft constraint weights
    weight_consecutive_limit: float = 10.0
    weight_paired_classes: float = 8.0
    weight_exam_avoidance: float = 7.0
    weight_time_preference: float = 5.0
    weight_room_utilization: float = 3.0
    weight_preserve_existing: float = 6.0


# ============================================================================
# DATA STRUCTURES — Internal
# ============================================================================

@dataclass
class Gene:
    """
    One session assignment in the chromosome.

    Each class with sessions_per_week=N will have N genes per week
    across the date range.
    """
    class_id: UUID
    session_date: date
    day: str               # "monday" .. "sunday"
    time_slots: List[int]  # e.g. [1, 2]
    room_id: Optional[UUID]
    session_index: int     # Nth session of this class in the overall schedule


# An Individual is simply a list of genes (one complete timetable)
Individual = List[Gene]


@dataclass
class GAResult:
    """Output of run_ga()."""
    best_individual: Individual
    fitness: float
    hard_violations: int
    soft_score: float
    generations_run: int
    fitness_history: List[float] = field(default_factory=list)


# ============================================================================
# HELPER LOOKUPS — built once per GA run
# ============================================================================

@dataclass
class _Lookups:
    """Pre-computed lookup tables to speed up fitness evaluation."""
    class_map: Dict[UUID, GAClassInput]                    # class_id → class
    room_map: Dict[UUID, GARoomInput]                      # room_id → room
    room_ids: List[UUID]                                   # all room ids
    eligible_rooms: Dict[UUID, List[UUID]]                 # class_id → rooms with enough capacity
    unavail_set: Set[Tuple[UUID, date, int]]               # (teacher_id, date, slot)
    unavail_full_day: Set[Tuple[UUID, date]]                # (teacher_id, date) blocked whole day
    fixed_times: Dict[UUID, List[Tuple[str, List[int]]]]   # class_id → [(day, slots)]
    paired_classes: List[Tuple[UUID, UUID]]
    exam_set: Set[Tuple[UUID, date]]                       # (class_id, date)
    existing_map: Dict[Tuple[UUID, date], List[int]]       # (class_id, date) → slots
    time_slot_configs: List[TimeSlotConfig]
    all_slot_numbers: List[int]
    schedule_dates: List[date]                              # all dates in the range


def _build_lookups(
    classes: List[GAClassInput],
    rooms: List[GARoomInput],
    constraints: GAConstraintInput,
    time_slots_config: List[TimeSlotConfig],
    date_range: Tuple[date, date],
) -> _Lookups:
    """Build pre-computed lookup structures."""

    class_map = {c.class_id: c for c in classes}
    room_map = {r.room_id: r for r in rooms}
    room_ids = [r.room_id for r in rooms]

    # Eligible rooms per class (rooms with capacity >= class max_students)
    eligible_rooms: Dict[UUID, List[UUID]] = {}
    for c in classes:
        eligible = [r.room_id for r in rooms if r.capacity >= c.max_students]
        if not eligible:
            # Fallback: include all rooms (will incur hard penalty in fitness)
            eligible = room_ids[:]
        eligible_rooms[c.class_id] = eligible

    # Teacher unavailability → fast set lookups
    unavail_set: Set[Tuple[UUID, date, int]] = set()
    unavail_full_day: Set[Tuple[UUID, date]] = set()
    for tid, entries in constraints.teacher_unavailability.items():
        for d, slots in entries:
            if not slots:
                unavail_full_day.add((tid, d))
            else:
                for s in slots:
                    unavail_set.add((tid, d, s))

    # Exam dates
    exam_set: Set[Tuple[UUID, date]] = set()
    for cid, dates in constraints.exam_dates.items():
        for d in dates:
            exam_set.add((cid, d))

    # Existing sessions map (for preserve-existing soft constraint)
    existing_map: Dict[Tuple[UUID, date], List[int]] = {}
    for es in constraints.existing_sessions:
        key = (es["class_id"], es["session_date"])
        existing_map[key] = es["time_slots"]

    # All dates in range
    start, end = date_range
    schedule_dates = []
    d = start
    while d <= end:
        schedule_dates.append(d)
        d += timedelta(days=1)

    all_slot_numbers = sorted([ts.slot_number for ts in time_slots_config])

    return _Lookups(
        class_map=class_map,
        room_map=room_map,
        room_ids=room_ids,
        eligible_rooms=eligible_rooms,
        unavail_set=unavail_set,
        unavail_full_day=unavail_full_day,
        fixed_times=constraints.class_fixed_times,
        paired_classes=constraints.paired_classes,
        exam_set=exam_set,
        existing_map=existing_map,
        time_slot_configs=time_slots_config,
        all_slot_numbers=all_slot_numbers,
        schedule_dates=schedule_dates,
    )


# ============================================================================
# POPULATION INITIALISATION
# ============================================================================

def _generate_sessions_for_class(
    cls: GAClassInput,
    lookups: _Lookups,
) -> List[Gene]:
    """
    Generate genes for ONE class across all weeks in the date range.

    Strategy:
      - If the class has fixed_schedule rules, honour them as much as possible.
      - Otherwise, randomly pick day+slots per week.
    """
    genes: List[Gene] = []
    dates = lookups.schedule_dates
    if not dates:
        return genes

    # Group dates by ISO week
    weeks: Dict[int, List[date]] = {}
    for d in dates:
        wk = d.isocalendar()[1]
        weeks.setdefault(wk, []).append(d)

    session_idx = 0

    for _wk_num, week_dates in sorted(weeks.items()):
        sessions_needed = cls.sessions_per_week
        sessions_placed = 0

        # ----- Try fixed schedule first -----
        fixed = lookups.fixed_times.get(cls.class_id, cls.fixed_schedule)
        if fixed:
            for rule in fixed:
                if sessions_placed >= sessions_needed:
                    break
                day_name = rule["day"] if isinstance(rule, dict) else rule[0]
                slots = rule["slots"] if isinstance(rule, dict) else rule[1]
                # Find matching date in this week
                for d in week_dates:
                    if DAYS[d.weekday()] == day_name:
                        room_id = _pick_room(cls, lookups)
                        genes.append(Gene(
                            class_id=cls.class_id,
                            session_date=d,
                            day=day_name,
                            time_slots=list(slots),
                            room_id=room_id,
                            session_index=session_idx,
                        ))
                        session_idx += 1
                        sessions_placed += 1
                        break

        # ----- Fill remaining with random -----
        available_dates = [d for d in week_dates if d.weekday() < 6]  # prefer Mon–Sat
        if not available_dates:
            available_dates = week_dates[:]

        attempts = 0
        max_attempts = sessions_needed * 10
        while sessions_placed < sessions_needed and attempts < max_attempts:
            attempts += 1
            d = random.choice(available_dates)
            day_name = DAYS[d.weekday()]

            # Pick slot count (1–3 consecutive slots)
            n_slots = random.choice([1, 2])
            max_start = max(lookups.all_slot_numbers) - n_slots + 1
            if max_start < min(lookups.all_slot_numbers):
                max_start = min(lookups.all_slot_numbers)
            start_slot = random.randint(min(lookups.all_slot_numbers), max_start)
            slots = list(range(start_slot, start_slot + n_slots))

            # Apply time-period preference probabilistically
            if cls.preferred_time_period and random.random() < 0.7:
                preferred_slots = TIME_PERIODS.get(cls.preferred_time_period, set())
                if preferred_slots:
                    filtered = [s for s in lookups.all_slot_numbers if s in preferred_slots]
                    if filtered:
                        max_s = max(filtered) - n_slots + 1
                        if max_s >= min(filtered):
                            start_slot = random.randint(min(filtered), max_s)
                            slots = list(range(start_slot, start_slot + n_slots))

            # Check for duplicate day+slots in same week for this class
            dup = False
            for g in genes:
                if g.class_id == cls.class_id and g.session_date == d and g.time_slots == slots:
                    dup = True
                    break
            if dup:
                continue

            room_id = _pick_room(cls, lookups)
            genes.append(Gene(
                class_id=cls.class_id,
                session_date=d,
                day=day_name,
                time_slots=list(slots),
                room_id=room_id,
                session_index=session_idx,
            ))
            session_idx += 1
            sessions_placed += 1

    return genes


def _pick_room(cls: GAClassInput, lookups: _Lookups) -> Optional[UUID]:
    """Pick a room for a class — prefer assigned room, else random eligible."""
    eligible = lookups.eligible_rooms.get(cls.class_id, [])
    if cls.room_id and cls.room_id in eligible:
        # 60% chance to use preferred room, 40% explore others
        if random.random() < 0.6:
            return cls.room_id
    if eligible:
        return random.choice(eligible)
    if lookups.room_ids:
        return random.choice(lookups.room_ids)
    return None


def create_random_individual(
    classes: List[GAClassInput],
    lookups: _Lookups,
) -> Individual:
    """Create one random timetable (individual)."""
    genes: List[Gene] = []
    for cls in classes:
        genes.extend(_generate_sessions_for_class(cls, lookups))
    return genes


# ============================================================================
# FITNESS FUNCTION
# ============================================================================

def evaluate_fitness(
    individual: Individual,
    lookups: _Lookups,
    config: GAConfig,
) -> Tuple[float, int, float]:
    """
    Evaluate fitness of an individual.

    Returns:
        (fitness_score, hard_violations, soft_score)
    """
    hard_violations = _count_hard_violations(individual, lookups)
    soft_score = _compute_soft_score(individual, lookups, config)
    fitness = -hard_violations * HARD_WEIGHT + soft_score
    return fitness, hard_violations, soft_score


# ---- Hard Constraints ----

def _count_hard_violations(individual: Individual, lookups: _Lookups) -> int:
    """Count total hard constraint violations."""
    violations = 0

    # Index: (teacher_id, date, slot) → count
    teacher_slots: Dict[Tuple[UUID, date, int], int] = {}
    # Index: (room_id, date, slot) → count
    room_slots: Dict[Tuple[UUID, date, int], int] = {}

    for gene in individual:
        cls = lookups.class_map.get(gene.class_id)
        if not cls:
            continue
        teacher_id = cls.teacher_id

        for slot in gene.time_slots:
            # --- 1. Teacher clash ---
            t_key = (teacher_id, gene.session_date, slot)
            teacher_slots[t_key] = teacher_slots.get(t_key, 0) + 1

            # --- 2. Room clash ---
            if gene.room_id:
                r_key = (gene.room_id, gene.session_date, slot)
                room_slots[r_key] = room_slots.get(r_key, 0) + 1

            # --- 3. Teacher unavailable ---
            if (teacher_id, gene.session_date) in lookups.unavail_full_day:
                violations += 1
            elif (teacher_id, gene.session_date, slot) in lookups.unavail_set:
                violations += 1

        # --- 4. Class fixed time (must match) ---
        fixed_rules = lookups.fixed_times.get(gene.class_id, [])
        if fixed_rules:
            # Check if this gene's day+slots match any fixed rule
            matched = False
            for rule in fixed_rules:
                r_day = rule["day"] if isinstance(rule, dict) else rule[0]
                r_slots = rule["slots"] if isinstance(rule, dict) else rule[1]
                if gene.day == r_day and sorted(gene.time_slots) == sorted(r_slots):
                    matched = True
                    break
            # Only penalise if class has fixed rules for THIS day
            day_rules = [
                r for r in fixed_rules
                if (r["day"] if isinstance(r, dict) else r[0]) == gene.day
            ]
            if day_rules and not matched:
                violations += 1

        # --- 5. Room capacity ---
        if gene.room_id and cls:
            room = lookups.room_map.get(gene.room_id)
            if room and cls.max_students > room.capacity:
                violations += 1

    # Count clashes (where count > 1)
    for count in teacher_slots.values():
        if count > 1:
            violations += count - 1  # Each extra is a clash

    for count in room_slots.values():
        if count > 1:
            violations += count - 1

    return violations


# ---- Soft Constraints ----

def _compute_soft_score(
    individual: Individual,
    lookups: _Lookups,
    config: GAConfig,
) -> float:
    """Compute soft constraint bonus score (higher is better)."""
    score = 0.0

    # Pre-group genes by (teacher, date) for consecutive-limit check
    teacher_day_slots: Dict[Tuple[UUID, date], List[int]] = {}
    for gene in individual:
        cls = lookups.class_map.get(gene.class_id)
        if not cls:
            continue
        key = (cls.teacher_id, gene.session_date)
        teacher_day_slots.setdefault(key, []).extend(gene.time_slots)

    # --- 1. Consecutive limit: teacher NOT teaching > 3 consecutive slots in a day ---
    for (tid, d), slots in teacher_day_slots.items():
        sorted_slots = sorted(set(slots))
        max_consecutive = _max_consecutive_count(sorted_slots)
        if max_consecutive <= 3:
            score += config.weight_consecutive_limit

    # --- 2. Paired classes: both in same time period on same date ---
    gene_index: Dict[Tuple[UUID, date], List[int]] = {}
    for gene in individual:
        key = (gene.class_id, gene.session_date)
        gene_index.setdefault(key, []).extend(gene.time_slots)

    for c1, c2 in lookups.paired_classes:
        for d in lookups.schedule_dates:
            slots1 = gene_index.get((c1, d))
            slots2 = gene_index.get((c2, d))
            if slots1 and slots2:
                period1 = _get_time_period(slots1)
                period2 = _get_time_period(slots2)
                if period1 and period1 == period2:
                    score += config.weight_paired_classes

    # --- 3. Exam avoidance: class NOT scheduled on exam dates ---
    for gene in individual:
        if (gene.class_id, gene.session_date) in lookups.exam_set:
            pass  # No bonus (or could add negative, but we keep it simple)
        else:
            # Only add bonus if this class actually has exam dates registered
            if gene.class_id in {cid for cid, _ in lookups.exam_set}:
                score += config.weight_exam_avoidance

    # --- 4. Time preference: class scheduled in preferred period ---
    for gene in individual:
        cls = lookups.class_map.get(gene.class_id)
        if cls and cls.preferred_time_period:
            period = _get_time_period(gene.time_slots)
            if period == cls.preferred_time_period:
                score += config.weight_time_preference

    # --- 5. Room utilisation: ratio in [0.6, 0.9] is ideal ---
    for gene in individual:
        if gene.room_id:
            cls = lookups.class_map.get(gene.class_id)
            room = lookups.room_map.get(gene.room_id)
            if cls and room and room.capacity > 0:
                ratio = cls.max_students / room.capacity
                if 0.6 <= ratio <= 0.9:
                    score += config.weight_room_utilization

    # --- 6. Preserve existing: session keeps same day+slots as DB ---
    for gene in individual:
        existing_slots = lookups.existing_map.get((gene.class_id, gene.session_date))
        if existing_slots and sorted(gene.time_slots) == sorted(existing_slots):
            score += config.weight_preserve_existing

    return score


def _max_consecutive_count(sorted_slots: List[int]) -> int:
    """Return the length of the longest consecutive run in sorted slot numbers."""
    if not sorted_slots:
        return 0
    max_run = 1
    current_run = 1
    for i in range(1, len(sorted_slots)):
        if sorted_slots[i] == sorted_slots[i - 1] + 1:
            current_run += 1
            max_run = max(max_run, current_run)
        else:
            current_run = 1
    return max_run


def _get_time_period(slots: List[int]) -> Optional[str]:
    """Determine dominant time period for a list of slots."""
    if not slots:
        return None
    slot_set = set(slots)
    for period_name, period_slots in TIME_PERIODS.items():
        if slot_set.issubset(period_slots):
            return period_name
    # Mixed — use majority
    counts = {p: len(slot_set & ps) for p, ps in TIME_PERIODS.items()}
    best = max(counts, key=counts.get)  # type: ignore
    return best if counts[best] > 0 else None


# ============================================================================
# SELECTION
# ============================================================================

def tournament_select(
    population: List[Individual],
    fitness_scores: List[float],
    tournament_size: int,
) -> Individual:
    """Select an individual via tournament selection."""
    indices = random.sample(range(len(population)), min(tournament_size, len(population)))
    best_idx = max(indices, key=lambda i: fitness_scores[i])
    return population[best_idx]


# ============================================================================
# CROSSOVER — Uniform Crossover by Class
# ============================================================================

def crossover(
    parent1: Individual,
    parent2: Individual,
    classes: List[GAClassInput],
) -> Tuple[Individual, Individual]:
    """
    Uniform crossover grouped by class.

    For ~50% of classes, child1 takes genes from parent1
    and child2 takes genes from parent2. For the rest, swap.
    """
    # Group genes by class_id
    p1_by_class: Dict[UUID, List[Gene]] = {}
    p2_by_class: Dict[UUID, List[Gene]] = {}

    for g in parent1:
        p1_by_class.setdefault(g.class_id, []).append(g)
    for g in parent2:
        p2_by_class.setdefault(g.class_id, []).append(g)

    child1_genes: List[Gene] = []
    child2_genes: List[Gene] = []

    all_class_ids = set(p1_by_class.keys()) | set(p2_by_class.keys())

    for cid in all_class_ids:
        g1 = p1_by_class.get(cid, [])
        g2 = p2_by_class.get(cid, [])

        if random.random() < 0.5:
            child1_genes.extend(copy.deepcopy(g1) if g1 else copy.deepcopy(g2))
            child2_genes.extend(copy.deepcopy(g2) if g2 else copy.deepcopy(g1))
        else:
            child1_genes.extend(copy.deepcopy(g2) if g2 else copy.deepcopy(g1))
            child2_genes.extend(copy.deepcopy(g1) if g1 else copy.deepcopy(g2))

    return child1_genes, child2_genes


# ============================================================================
# MUTATION
# ============================================================================

def mutate(
    individual: Individual,
    mutation_rate: float,
    lookups: _Lookups,
) -> None:
    """
    In-place mutation. Each gene has `mutation_rate` probability of being mutated.

    Mutation types (chosen randomly):
        1. Time shift — change day + time_slots
        2. Room swap — change room to another eligible one
        3. Slot shift — keep same day, change time_slots
    """
    for gene in individual:
        if random.random() >= mutation_rate:
            continue

        mutation_type = random.choice(["time_shift", "room_swap", "slot_shift"])
        cls = lookups.class_map.get(gene.class_id)

        if mutation_type == "time_shift":
            # Pick a new random date from the schedule
            if lookups.schedule_dates:
                new_date = random.choice(lookups.schedule_dates)
                gene.session_date = new_date
                gene.day = DAYS[new_date.weekday()]
            # Also change slots
            _randomise_slots(gene, lookups)

        elif mutation_type == "room_swap":
            eligible = lookups.eligible_rooms.get(gene.class_id, lookups.room_ids)
            if eligible:
                gene.room_id = random.choice(eligible)

        elif mutation_type == "slot_shift":
            _randomise_slots(gene, lookups)


def _randomise_slots(gene: Gene, lookups: _Lookups) -> None:
    """Randomise time_slots for a gene while keeping slot count the same."""
    n_slots = len(gene.time_slots) if gene.time_slots else random.choice([1, 2])
    all_slots = lookups.all_slot_numbers
    if not all_slots:
        return
    max_start = max(all_slots) - n_slots + 1
    if max_start < min(all_slots):
        max_start = min(all_slots)
    start = random.randint(min(all_slots), max_start)
    gene.time_slots = list(range(start, start + n_slots))


# ============================================================================
# ELITISM
# ============================================================================

def elitism(
    population: List[Individual],
    fitness_scores: List[float],
    count: int,
) -> List[Individual]:
    """Return deep copies of the top `count` individuals."""
    indexed = sorted(
        zip(range(len(population)), fitness_scores),
        key=lambda x: x[1],
        reverse=True,
    )
    return [copy.deepcopy(population[i]) for i, _ in indexed[:count]]


# ============================================================================
# CONVERGENCE CHECK
# ============================================================================

def check_convergence(
    fitness_history: List[float],
    window: int,
    current_hard_violations: int,
) -> bool:
    """
    Returns True if we should stop early.

    Conditions:
        1. hard_violations == 0  AND
        2. fitness has not improved by > 0.1% in the last `window` generations
    """
    if current_hard_violations > 0:
        return False

    if len(fitness_history) < window:
        return False

    recent = fitness_history[-window:]
    if recent[-1] <= 0:
        return False

    improvement = abs(recent[-1] - recent[0]) / abs(recent[-1])
    return improvement < 0.001  # Less than 0.1% improvement


# ============================================================================
# MAIN GA LOOP
# ============================================================================

def run_ga(
    classes: List[GAClassInput],
    rooms: List[GARoomInput],
    constraints: GAConstraintInput,
    config: GAConfig,
    time_slots_config: List[TimeSlotConfig],
    date_range: Tuple[date, date],
    progress_callback: Optional[Any] = None,
) -> GAResult:
    """
    Run the Genetic Algorithm schedule optimizer.

    Args:
        classes: List of classes to schedule.
        rooms: List of available rooms.
        constraints: Hard/soft constraints.
        config: GA hyperparameters.
        time_slots_config: System time-slot definitions.
        date_range: (start_date, end_date) tuple.
        progress_callback: Optional callable(generation, best_fitness, hard_violations)
                           for progress reporting.

    Returns:
        GAResult with the best timetable found.
    """
    if not classes:
        raise ValueError("No classes provided to GA scheduler")
    if not rooms:
        raise ValueError("No rooms provided to GA scheduler")

    logger.info(
        f"Starting GA: {len(classes)} classes, {len(rooms)} rooms, "
        f"pop={config.population_size}, gens={config.generations}"
    )

    # Build lookups
    lookups = _build_lookups(classes, rooms, constraints, time_slots_config, date_range)

    # 1. Initialise population
    population: List[Individual] = []
    for _ in range(config.population_size):
        ind = create_random_individual(classes, lookups)
        population.append(ind)

    best_individual: Optional[Individual] = None
    best_fitness = float("-inf")
    best_hard = 0
    best_soft = 0.0
    fitness_history: List[float] = []

    # 2. Evolve
    gen = 0
    for gen in range(config.generations):
        # --- Evaluate ---
        evals = [evaluate_fitness(ind, lookups, config) for ind in population]
        fitness_scores = [e[0] for e in evals]

        # --- Track best ---
        gen_best_idx = max(range(len(population)), key=lambda i: fitness_scores[i])
        gen_best_fit, gen_best_hard, gen_best_soft = evals[gen_best_idx]

        if gen_best_fit > best_fitness:
            best_individual = copy.deepcopy(population[gen_best_idx])
            best_fitness = gen_best_fit
            best_hard = gen_best_hard
            best_soft = gen_best_soft

        fitness_history.append(best_fitness)

        # --- Progress report ---
        if progress_callback:
            try:
                progress_callback(gen, best_fitness, best_hard)
            except Exception:
                pass

        if gen % 50 == 0:
            logger.info(
                f"Gen {gen}: best_fitness={best_fitness:.2f}, "
                f"hard={best_hard}, soft={best_soft:.2f}"
            )

        # --- Early stopping ---
        if check_convergence(fitness_history, config.convergence_window, best_hard):
            logger.info(f"Converged at generation {gen}")
            break

        # --- Create next generation ---
        next_gen = elitism(population, fitness_scores, config.elitism_count)

        while len(next_gen) < config.population_size:
            p1 = tournament_select(population, fitness_scores, config.tournament_size)
            p2 = tournament_select(population, fitness_scores, config.tournament_size)

            if random.random() < config.crossover_rate:
                c1, c2 = crossover(p1, p2, classes)
            else:
                c1, c2 = copy.deepcopy(p1), copy.deepcopy(p2)

            mutate(c1, config.mutation_rate, lookups)
            mutate(c2, config.mutation_rate, lookups)

            next_gen.append(c1)
            if len(next_gen) < config.population_size:
                next_gen.append(c2)

        population = next_gen[:config.population_size]

    # 3. Final evaluation of best
    if best_individual is None:
        # Should not happen, but handle edge case
        best_individual = population[0]
        best_fitness, best_hard, best_soft = evaluate_fitness(
            best_individual, lookups, config
        )

    logger.info(
        f"GA finished: {gen + 1} generations, "
        f"fitness={best_fitness:.2f}, hard={best_hard}, soft={best_soft:.2f}, "
        f"genes={len(best_individual)}"
    )

    return GAResult(
        best_individual=best_individual,
        fitness=best_fitness,
        hard_violations=best_hard,
        soft_score=best_soft,
        generations_run=gen + 1,
        fitness_history=fitness_history,
    )


# ============================================================================
# UTILITY — Convert result back to schedule-friendly dicts
# ============================================================================

def individual_to_session_dicts(
    individual: Individual,
    lookups: _Lookups,
) -> List[Dict[str, Any]]:
    """
    Convert the best individual into a list of session dictionaries
    ready for the service layer to save as GAScheduleProposal records.

    Each dict has:
        class_id, teacher_id, room_id, session_date, time_slots,
        start_time, end_time, is_conflict, conflict_details
    """
    # Pre-compute clash sets for conflict detection
    teacher_slots: Dict[Tuple[UUID, date, int], int] = {}
    room_slots: Dict[Tuple[UUID, date, int], int] = {}

    for gene in individual:
        cls = lookups.class_map.get(gene.class_id)
        if not cls:
            continue
        for slot in gene.time_slots:
            t_key = (cls.teacher_id, gene.session_date, slot)
            teacher_slots[t_key] = teacher_slots.get(t_key, 0) + 1
            if gene.room_id:
                r_key = (gene.room_id, gene.session_date, slot)
                room_slots[r_key] = room_slots.get(r_key, 0) + 1

    results: List[Dict[str, Any]] = []

    for gene in individual:
        cls = lookups.class_map.get(gene.class_id)
        if not cls:
            continue

        # Determine start_time / end_time from slots
        start_time, end_time = _slots_to_time_range(gene.time_slots, lookups.time_slot_configs)

        # Check if this gene has conflicts
        is_conflict = False
        conflict_details = None

        # Teacher clash?
        for slot in gene.time_slots:
            if teacher_slots.get((cls.teacher_id, gene.session_date, slot), 0) > 1:
                is_conflict = True
                conflict_details = {
                    "type": "teacher_clash",
                    "teacher_id": str(cls.teacher_id),
                    "date": str(gene.session_date),
                    "slot": slot,
                    "reason": f"Teacher has multiple sessions at slot {slot}",
                }
                break

        # Room clash?
        if not is_conflict and gene.room_id:
            for slot in gene.time_slots:
                if room_slots.get((gene.room_id, gene.session_date, slot), 0) > 1:
                    is_conflict = True
                    conflict_details = {
                        "type": "room_clash",
                        "room_id": str(gene.room_id),
                        "date": str(gene.session_date),
                        "slot": slot,
                        "reason": f"Room has multiple sessions at slot {slot}",
                    }
                    break

        # Teacher unavailable?
        if not is_conflict:
            if (cls.teacher_id, gene.session_date) in lookups.unavail_full_day:
                is_conflict = True
                conflict_details = {
                    "type": "teacher_unavailable",
                    "teacher_id": str(cls.teacher_id),
                    "date": str(gene.session_date),
                    "reason": "Teacher is unavailable for the entire day",
                }
            else:
                for slot in gene.time_slots:
                    if (cls.teacher_id, gene.session_date, slot) in lookups.unavail_set:
                        is_conflict = True
                        conflict_details = {
                            "type": "teacher_unavailable",
                            "teacher_id": str(cls.teacher_id),
                            "date": str(gene.session_date),
                            "slot": slot,
                            "reason": f"Teacher is unavailable at slot {slot}",
                        }
                        break

        # Room capacity?
        if not is_conflict and gene.room_id:
            room = lookups.room_map.get(gene.room_id)
            if room and cls.max_students > room.capacity:
                is_conflict = True
                conflict_details = {
                    "type": "room_capacity",
                    "room_id": str(gene.room_id),
                    "max_students": cls.max_students,
                    "room_capacity": room.capacity,
                    "reason": f"Class needs {cls.max_students} seats, room has {room.capacity}",
                }

        results.append({
            "class_id": gene.class_id,
            "teacher_id": cls.teacher_id,
            "room_id": gene.room_id,
            "session_date": gene.session_date,
            "time_slots": gene.time_slots,
            "start_time": start_time,
            "end_time": end_time,
            "lesson_topic": f"Lesson {gene.session_index + 1} - {cls.class_name}",
            "is_conflict": is_conflict,
            "conflict_details": conflict_details,
        })

    return results


def _slots_to_time_range(
    slots: List[int],
    time_slot_configs: List[TimeSlotConfig],
) -> Tuple[time, time]:
    """Convert slot numbers to (start_time, end_time)."""
    if not slots:
        # Fallback
        return time(8, 0), time(9, 30)

    sorted_slots = sorted(slots)
    config_map = {ts.slot_number: ts for ts in time_slot_configs}

    start_slot = config_map.get(sorted_slots[0])
    end_slot = config_map.get(sorted_slots[-1])

    if not start_slot or not end_slot:
        return time(8, 0), time(9, 30)

    return start_slot.start_time, end_slot.end_time
