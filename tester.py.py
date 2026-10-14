from squad.doctor import report


def test_report_has_isolation_levels():
    data = report()
    assert "isolation" in data
    assert "level_0" in data["isolation"]