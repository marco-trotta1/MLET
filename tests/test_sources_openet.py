from mlet.sources.openet import load_openet_ensemble


SAMPLE = (
    "    # comment line describing the file\n"
    "Site ID\tgeeSEBAL\tPT-JPL\tSSEBop\tSIMS\teeMETRIC\tDisALEXI\tEnsemble\tDATE\n"
    "ALARC2_Smith6\t1.4\t0.7\t0.1\t0.9\t1.2\t0.9\t1.0\t2018-02-07\n"
    "US-A32\t\t\t\t\t\t\t\t2018-02-08\n"
    "US-A32\t2.0\t2.1\t1.9\t2.2\t2.0\t2.1\t2.05\t2018-02-09\n"
)


def test_load_openet_ensemble(tmp_path):
    path = tmp_path / "daily_data.dat"
    path.write_text(SAMPLE)
    values = load_openet_ensemble(str(path))
    assert values[("ALARC2_Smith6", "2018-02-07")] == 1.0
    assert values[("US-A32", "2018-02-09")] == 2.05
    assert ("US-A32", "2018-02-08") not in values
    assert len(values) == 2
