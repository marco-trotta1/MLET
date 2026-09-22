"""Export source humidity values for the frozen model cohort."""
import json
from pathlib import Path
import pandas as pd
from openpyxl import load_workbook

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"docs/results/ml_transfer"


def main():
    d=pd.read_csv(OUT/"cohort.csv")
    folder=ROOT/"data/raw/flux_et/flux_ET_dataset"
    records=[]
    for station,group in d.groupby("station"):
        raw=pd.read_csv(folder/"daily_data_files"/f"{station}_daily_data.csv")
        for _,row in raw[raw.date.isin(group.date)].iterrows():
            records.append({"station":station,"date":row.date,"vp_kpa":row.get("vp"),
              "vpd_kpa":row.get("vpd"),"es_kpa":row.get("es"),"t_max_c":row.get("t_max")})
    audit=pd.DataFrame(records)
    assert len(audit)==len(d)
    audit.to_csv(OUT/"humidity_audit.csv",index=False)
    book=load_workbook(folder/"variable_explanation.xlsx",read_only=True,data_only=True)
    units=[list(row) for sheet in book for row in sheet.values if "vpd" in row or "vp" in row]
    book.close()
    negative=audit[audit.vp_kpa<0]
    summary={"source_unit_rows":units,"negative_vp_rows":len(negative),
             "negative_vp_stations":sorted(negative.station.unique()),
             "by_station":negative.groupby("station").agg(n=("date","size"),
              vp_min=("vp_kpa","min"),vp_max=("vp_kpa","max"),
              vpd_min=("vpd_kpa","min"),vpd_max=("vpd_kpa","max")).to_dict("index")}
    (OUT/"humidity_summary.json").write_text(json.dumps(summary,indent=2))
    print("Humidity audit:",len(negative),"negative-vapor-pressure rows at",negative.station.nunique(),"stations")


if __name__=="__main__":main()
