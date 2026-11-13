"""Geocode official SPBU addresses with public Nominatim (one request/sec).

Output coordinates are CANDIDATES only. Review every result against OSM imagery
and the official station identity before changing location_status to VERIFIED.
Respect Nominatim usage policy; do not parallelize or run repeatedly.
"""
from __future__ import annotations
import argparse, time
from pathlib import Path
import pandas as pd
import requests

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--input',type=Path,default=Path('data/spbu_kota_bandung_esdm_2025.csv'))
    p.add_argument('--output',type=Path,default=Path('data/spbu_kota_bandung_geocoded_candidates.csv'))
    p.add_argument('--pause',type=float,default=1.1)
    args=p.parse_args()
    df=pd.read_csv(args.input).fillna('')
    session=requests.Session()
    session.headers.update({'User-Agent':'GEO-FUEL-academic-prototype/1.0 (contact: researcher)'})
    lats=[]; lons=[]; displays=[]; statuses=[]
    for i,row in df.iterrows():
        query=f"SPBU {row['official_spbu_code']}, {row['address']}"
        try:
            response=session.get('https://nominatim.openstreetmap.org/search',
                params={'q':query,'format':'jsonv2','limit':1,'countrycodes':'id'},timeout=30)
            response.raise_for_status(); found=response.json()
            if found:
                item=found[0]
                lats.append(float(item['lat'])); lons.append(float(item['lon']))
                displays.append(item.get('display_name','')); statuses.append('OSM_GEOCODE_CANDIDATE')
            else:
                lats.append(''); lons.append(''); displays.append(''); statuses.append('NOT_FOUND')
        except Exception as exc:
            lats.append(''); lons.append(''); displays.append(str(exc)); statuses.append('GEOCODE_ERROR')
        print(f"[{i+1}/{len(df)}] {row['official_spbu_code']}: {statuses[-1]}",flush=True)
        time.sleep(max(1.1,args.pause))
    df['lat_candidate']=lats; df['lon_candidate']=lons
    df['geocode_display_name']=displays; df['location_status']=statuses
    df['location_source']='OpenStreetMap Nominatim'; df['geocoded_at']=pd.Timestamp.now(tz='Asia/Jakarta').isoformat()
    args.output.parent.mkdir(parents=True,exist_ok=True); df.to_csv(args.output,index=False,encoding='utf-8-sig')
    print(f"Saved {args.output}. Coordinates are candidates, not verified facility coordinates.")
    print('Attribution: © OpenStreetMap contributors, ODbL 1.0; https://www.openstreetmap.org/copyright')
if __name__=='__main__': main()
