"""Create complete, explicitly SIMULATED operations data for geocoded SPBU candidates.

This does NOT estimate actual Pertamina stock, tank capacities, sales or lead times.
It creates repeatable experiment scenarios after public facility coordinates exist.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import numpy as np
import pandas as pd

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--input',type=Path,default=Path('data/spbu_kota_bandung_geocoded_candidates.csv'))
    p.add_argument('--stations-output',type=Path,default=Path('data/stations_synthetic.csv'))
    p.add_argument('--sales-output',type=Path,default=Path('data/daily_sales_synthetic.csv'))
    p.add_argument('--fleet-output',type=Path,default=Path('data/fleet_synthetic.csv'))
    p.add_argument('--days',type=int,default=30); p.add_argument('--seed',type=int,default=42)
    args=p.parse_args()
    if args.days<14: p.error('--days minimal 14 untuk ringkasan statistik demand')
    src=pd.read_csv(args.input)
    required={'official_spbu_code','name','address','lat_candidate','lon_candidate'}
    missing=required-set(src.columns)
    if missing: raise ValueError(f'Kolom input kurang: {sorted(missing)}')
    src=src.dropna(subset=['lat_candidate','lon_candidate']).copy()
    if src.empty: raise ValueError('Tidak ada koordinat kandidat. Jalankan geocode_official_spbu.py lebih dahulu.')
    src['lat']=pd.to_numeric(src['lat_candidate'],errors='raise'); src['lon']=pd.to_numeric(src['lon_candidate'],errors='raise')
    if not src['lat'].between(-7.1,-6.7).all() or not src['lon'].between(107.3,108.0).all():
        raise ValueError('Koordinat di luar rentang pemeriksaan kasar Bandung; periksa hasil geocoding.')
    rng=np.random.default_rng(args.seed); stations=[]; sales=[]
    start=pd.Timestamp('2026-10-15')
    for r in src.itertuples():
        capacity=int(rng.choice([30000,35000,40000]))
        demand=float(rng.uniform(7000,13000))
        initial=float(round(rng.uniform(0.18,0.55)*capacity,2))
        vals=[]
        for day in range(args.days):
            date=start+pd.Timedelta(days=day)
            weekday=1.06 if date.dayofweek in (4,5) else (0.94 if date.dayofweek==0 else 1.0)
            value=max(0.0,round(demand*weekday*float(rng.normal(1.0,0.08)),2))
            vals.append(value)
            sales.append({'station_id':str(r.official_spbu_code),'date':date.date().isoformat(),
                'sales_liters':value,'data_status':'SIMULATED','source_note':'Synthetic; not actual station sales'})
        stations.append({'station_id':str(r.official_spbu_code),'name':str(r.name),'address':str(r.address),
            'lat':float(r.lat),'lon':float(r.lon),'capacity_liters':capacity,'initial_stock_liters':initial,
            'stock_as_of':'SIMULATED_SCENARIO','daily_demand_liters':float(np.mean(vals)),
            'demand_std_liters_per_day':float(np.std(vals,ddof=1)), 'mean_lead_time_days':0.35,
            'lead_time_std_days':0.10,'service_level_z':1.65,'window_start':6,'window_end':22,
            'data_status':'SIMULATED','location_status':'OSM_GEOCODE_CANDIDATE',
            'location_source':'OpenStreetMap Nominatim; manual validation required'})
    pd.DataFrame(stations).to_csv(args.stations_output,index=False,encoding='utf-8-sig')
    pd.DataFrame(sales).to_csv(args.sales_output,index=False,encoding='utf-8-sig')
    fleet=pd.DataFrame([('MT-SIM-01',8000),('MT-SIM-02',16000),('MT-SIM-03',24000),
                        ('MT-SIM-04',16000),('MT-SIM-05',24000),('MT-SIM-06',8000)],
                       columns=['vehicle_id','capacity_liters'])
    fleet['data_status']='SIMULATED'; fleet.to_csv(args.fleet_output,index=False,encoding='utf-8-sig')
    print(f"SPBU candidates: {len(stations)} | sales rows: {len(sales)} | days/station: {args.days}")
    print('All operational values are SIMULATED. Do not label them as Pertamina actual data.')
if __name__=='__main__': main()
