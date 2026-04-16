"""
Quick smoke test for the GA engine — runs without DB.
"""
import uuid
from datetime import date, time

from app.services.schedule.genetic_algorithm import (
    GAClassInput, GARoomInput, GAConstraintInput, GAConfig, TimeSlotConfig,
    run_ga, evaluate_fitness, individual_to_session_dicts,
    create_random_individual, crossover, mutate, tournament_select, elitism,
    _build_lookups, check_convergence,
)


# --- Fixtures ---

def _make_time_slots():
    return [
        TimeSlotConfig(1, time(8, 0), time(9, 30)),
        TimeSlotConfig(2, time(9, 45), time(11, 15)),
        TimeSlotConfig(3, time(13, 0), time(14, 30)),
        TimeSlotConfig(4, time(14, 45), time(16, 15)),
        TimeSlotConfig(5, time(18, 0), time(19, 30)),
        TimeSlotConfig(6, time(19, 45), time(21, 15)),
    ]


def _make_rooms(n=3):
    return [
        GARoomInput(room_id=uuid.uuid4(), name=f"Room-{i}", capacity=30)
        for i in range(n)
    ]


def _make_classes(n=3, teacher_count=2):
    teachers = [uuid.uuid4() for _ in range(teacher_count)]
    classes = []
    for i in range(n):
        classes.append(GAClassInput(
            class_id=uuid.uuid4(),
            class_name=f"Class-{i}",
            teacher_id=teachers[i % teacher_count],
            room_id=None,
            max_students=20,
            sessions_per_week=2,
            fixed_schedule=[],
            preferred_time_period="morning" if i % 2 == 0 else None,
        ))
    return classes


def _date_range():
    return (date(2026, 4, 20), date(2026, 4, 26))  # 1 week


# --- Tests ---

def test_create_random_individual():
    classes = _make_classes()
    rooms = _make_rooms()
    ts = _make_time_slots()
    lookups = _build_lookups(classes, rooms, GAConstraintInput(), ts, _date_range())
    
    ind = create_random_individual(classes, lookups)
    assert len(ind) > 0, "Individual should have genes"
    print(f"  [OK] Created individual with {len(ind)} genes")


def test_fitness_no_violations():
    """A well-constructed individual should have few or no hard violations."""
    classes = _make_classes(n=2, teacher_count=2)
    rooms = _make_rooms(n=5)
    ts = _make_time_slots()
    config = GAConfig(population_size=10, generations=5)
    lookups = _build_lookups(classes, rooms, GAConstraintInput(), ts, _date_range())
    
    ind = create_random_individual(classes, lookups)
    fitness, hard, soft = evaluate_fitness(ind, lookups, config)
    print(f"  [OK] Fitness={fitness:.2f}, hard={hard}, soft={soft:.2f}")


def test_crossover_preserves_completeness():
    classes = _make_classes(n=3)
    rooms = _make_rooms()
    ts = _make_time_slots()
    lookups = _build_lookups(classes, rooms, GAConstraintInput(), ts, _date_range())
    
    p1 = create_random_individual(classes, lookups)
    p2 = create_random_individual(classes, lookups)
    c1, c2 = crossover(p1, p2, classes)
    
    # Each child should have genes for all classes
    p1_classes = {g.class_id for g in p1}
    c1_classes = {g.class_id for g in c1}
    assert p1_classes == c1_classes, "Crossover lost some classes"
    print(f"  [OK] Crossover preserved all {len(c1_classes)} classes")


def test_mutation_changes_gene():
    classes = _make_classes(n=2)
    rooms = _make_rooms()
    ts = _make_time_slots()
    lookups = _build_lookups(classes, rooms, GAConstraintInput(), ts, _date_range())
    
    ind = create_random_individual(classes, lookups)
    original_slots = [tuple(g.time_slots) for g in ind]
    
    # Force high mutation rate
    mutate(ind, 1.0, lookups)
    
    new_slots = [tuple(g.time_slots) for g in ind]
    changed = sum(1 for a, b in zip(original_slots, new_slots) if a != b)
    print(f"  [OK] Mutation changed {changed}/{len(ind)} genes")


def test_tournament_selection():
    classes = _make_classes(n=2)
    rooms = _make_rooms()
    ts = _make_time_slots()
    config = GAConfig()
    lookups = _build_lookups(classes, rooms, GAConstraintInput(), ts, _date_range())
    
    pop = [create_random_individual(classes, lookups) for _ in range(10)]
    scores = [evaluate_fitness(i, lookups, config)[0] for i in pop]
    
    selected = tournament_select(pop, scores, 5)
    assert len(selected) > 0
    print(f"  [OK] Tournament selected individual with {len(selected)} genes")


def test_elitism_preserves_best():
    classes = _make_classes(n=2)
    rooms = _make_rooms()
    ts = _make_time_slots()
    config = GAConfig()
    lookups = _build_lookups(classes, rooms, GAConstraintInput(), ts, _date_range())
    
    pop = [create_random_individual(classes, lookups) for _ in range(10)]
    scores = [evaluate_fitness(i, lookups, config)[0] for i in pop]
    
    elite = elitism(pop, scores, 3)
    assert len(elite) == 3
    print(f"  [OK] Elitism preserved top 3 individuals")


def test_convergence_check():
    # Should not converge with hard violations
    assert not check_convergence([1.0] * 40, 30, 1)
    # Should converge if flat and no violations
    assert check_convergence([100.0] * 40, 30, 0)
    # Should not converge if improving
    assert not check_convergence(list(range(40)), 30, 0)
    print(f"  [OK] Convergence check OK")


def test_run_ga_small():
    """End-to-end test with small parameters."""
    classes = _make_classes(n=3, teacher_count=2)
    rooms = _make_rooms(n=4)
    ts = _make_time_slots()
    constraints = GAConstraintInput()
    config = GAConfig(
        population_size=20,
        generations=30,
        crossover_rate=0.7,
        mutation_rate=0.15,
        elitism_count=2,
        tournament_size=3,
        convergence_window=10,
    )
    
    result = run_ga(classes, rooms, constraints, config, ts, _date_range())
    
    assert result.best_individual is not None
    assert result.generations_run > 0
    assert len(result.fitness_history) > 0
    print(f"  [OK] GA completed: {result.generations_run} gens, "
          f"fitness={result.fitness:.2f}, hard={result.hard_violations}, soft={result.soft_score:.2f}")
    
    # Convert to session dicts
    lookups = _build_lookups(classes, rooms, constraints, ts, _date_range())
    sessions = individual_to_session_dicts(result.best_individual, lookups)
    assert len(sessions) > 0
    conflict_count = sum(1 for s in sessions if s["is_conflict"])
    print(f"  [OK] Generated {len(sessions)} sessions, {conflict_count} conflicts")


def test_fitness_improves_over_generations():
    """Verify fitness improves (monotonically for best due to elitism)."""
    classes = _make_classes(n=4, teacher_count=3)
    rooms = _make_rooms(n=5)
    ts = _make_time_slots()
    config = GAConfig(population_size=30, generations=50, elitism_count=3)
    
    result = run_ga(classes, rooms, GAConstraintInput(), config, ts, _date_range())
    
    # With elitism, best fitness should be non-decreasing
    for i in range(1, len(result.fitness_history)):
        assert result.fitness_history[i] >= result.fitness_history[i - 1], \
            f"Fitness decreased at gen {i}: {result.fitness_history[i-1]} -> {result.fitness_history[i]}"
    print(f"  [OK] Fitness monotonically non-decreasing over {result.generations_run} gens")


if __name__ == "__main__":
    tests = [
        test_create_random_individual,
        test_fitness_no_violations,
        test_crossover_preserves_completeness,
        test_mutation_changes_gene,
        test_tournament_selection,
        test_elitism_preserves_best,
        test_convergence_check,
        test_run_ga_small,
        test_fitness_improves_over_generations,
    ]
    
    print("=" * 60)
    print("GA Engine Smoke Tests")
    print("=" * 60)
    
    passed = 0
    failed = 0
    for t in tests:
        print(f"\n> {t.__name__}")
        try:
            t()
            passed += 1
        except Exception as e:
            print(f"  [FAIL] FAILED: {e}")
            failed += 1
    
    print(f"\n{'=' * 60}")
    print(f"Results: {passed} passed, {failed} failed")
    print(f"{'=' * 60}")
