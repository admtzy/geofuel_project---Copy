"""Unduh lokasi SPBU dari OpenStreetMap Overpass untuk wilayah Bandung.

Contoh: python scripts/import_spbu_osm.py --region bandung-raya
Output: data/spbu_osm_bandung_raya.csv dan .xlsx (jika openpyxl tersedia).
Data lokasi OSM bukan data stok/penjualan; lengkapi kolom operasional sebelum simulasi.
"""
from __future__ import annotations
import argparse, json, time
from pathlib import Path
import pandas as pd
import requests

REGIONS = {
    "kota-bandung": "area['name'='Kota Bandung']['admin_level'='6']->.a;",
    "bandung-raya": "area['name'='Kota Bandung']['admin_level'='6']->.a; area['name'='Kabupaten Bandung']['admin_level'='6']->.b; area['name'='Kota Cimahi']['admin_level'='6']->.c; area['name'='Kabupaten Bandung Barat']['admin_level'='6']->.d;",
}
ENDPOINTS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter"]

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--region',choices=REGIONS,default='kota-bandung')
    ap.add_argument('--output',type=Path,default=Path('data/spbu_osm_bandung.csv'))
    args=ap.parse_args()
    area_stmt=REGIONS[args.region]
    area_refs='.a' if args.region=='kota-bandung' else '.a,.b,.c,.d'
    query=f'''[out:json][timeout:180];\n{area_stmt}\n( nwr["amenity"="fuel"](area.a);'''
    if args.region!='kota-bandung':
        query='[out:json][timeout:180];\n'+area_stmt+'\n( nwr["amenity"="fuel"](area.a); nwr["amenity"="fuel"](area.b); nwr["amenity"="fuel"](area.c); nwr["amenity"="fuel"](area.d); ); out center tags;'
    else: query += ' ); out center tags;'
    errors=[]; data=None
    for url in ENDPOINTS:
        try:
            r=requests.post(url,data={'data':query},headers={'User-Agent':'GEOFUEL-research/1.0 (academic use)'},timeout=210)
            r.raise_for_status(); data=r.json(); break
        except Exception as e: errors.append(f'{url}: {e}'); time.sleep(2)
    if data is None: raise RuntimeError('Overpass tidak tersedia: '+' | '.join(errors))
    rows=[]
    for el in data.get('elements',[]):
        tags=el.get('tags',{}); lat=el.get('lat',el.get('center',{}).get('lat')); lon=el.get('lon',el.get('center',{}).get('lon'))
        if lat is None or lon is None: continue
        name=tags.get('name') or tags.get('brand') or f"SPBU OSM {el['type']}/{el['id']}"
        rows.append({'station_id':f"OSM_{el['type']}_{el['id']}",'name':name,'lat':lat,'lon':lon,'osm_type':el['type'],'osm_id':el['id'],'brand':tags.get('brand',''),'operator':tags.get('operator',''),'address':', '.join(x for x in [tags.get('addr:street'),tags.get('addr:suburb'),tags.get('addr:city')] if x),'capacity_liters':'','initial_stock_liters':'','daily_demand_liters':'','data_status':'OSM_LOCATION_ONLY'})
    df=pd.DataFrame(rows).drop_duplicates('station_id').sort_values(['name','station_id'])
    args.output.parent.mkdir(parents=True,exist_ok=True); df.to_csv(args.output,index=False,encoding='utf-8-sig')
    try: df.to_excel(args.output.with_suffix('.xlsx'),index=False)
    except ImportError: print('openpyxl belum terpasang; file XLSX dilewati (pip install openpyxl).')
    print(f'{len(df)} titik SPBU/fasilitas BBM ditemukan. CSV: {args.output}')
    print('Verifikasi manual: OSM bisa berisi SPBU tidak aktif/duplikat/tidak lengkap. Isi kapasitas, stok, dan demand sebelum menjalankan simulasi.')
    print('Atribusi: © OpenStreetMap contributors, ODbL 1.0 — https://www.openstreetmap.org/copyright')
if __name__=='__main__': main()
