from scripts.simulate_ranking import SCENARIOS, run_simulation


def test_synthetic_benchmark_has_multiple_distinct_professional_profiles():
    assert len(SCENARIOS) >= 8
    assert len({scenario.name for scenario in SCENARIOS}) == len(SCENARIOS)


def test_every_synthetic_profile_ranks_its_relevant_role_first():
    passed, total, failures = run_simulation()
    assert total >= 8
    assert passed == total, "\n".join(failures)
    assert not failures
