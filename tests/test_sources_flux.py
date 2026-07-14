from mlet.sources.flux import FluxDaily, load_flux_daily


HEADER = "date,ET,ET_corr,ET_gap,gridMET_ETo,t_avg,vpd,ws,ppt\n"
BODY = (
    "2017-06-01,4.9,5.1,False,6.5,24.0,1.8,2.1,0.0\n"
    "2017-06-02,,,True,5.4,23.0,1.5,1.9,0.0\n"
)


def test_load_flux_daily(tmp_path):
    path = tmp_path / "US-A32_daily_data.csv"
    path.write_text(HEADER + BODY)
    values = load_flux_daily(str(path))
    first = values["2017-06-01"]
    assert isinstance(first, FluxDaily)
    assert first.et_corr == 5.1 and first.et_gap is False and first.gridmet_eto == 6.5
    assert first.t_avg == 24.0 and first.vpd == 1.8
    assert values["2017-06-02"].et_corr is None
    assert values["2017-06-02"].et_gap is True
