from redocket.return_survival.estimator import _typical_return, survival_ladder


def test_censor_alone_does_not_count_as_a_return():
    ladder = survival_ladder([(2, False), (4, True), (4, False), (8, True)])
    assert ladder[0] == (2, 4, 0, 1, 1.0)
    assert ladder[1][:4] == (4, 3, 1, 1)
    assert _typical_return(ladder) == 8
