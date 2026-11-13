# Cara membuat input publik yang dapat dijalankan

## 1. Instal dependensi

Di PowerShell, dari folder `Geoful`:

```powershell
python -m pip install -r requirements.txt
```

Pastikan juga solver HiGHS tersedia jika ingin menjalankan model MILP. Periksa dengan:

```powershell
python scripts/check_solver.py
```

## 2. Bangun input SPBU dan armada

```powershell
python scripts/build_public_runnable_dataset.py
```

Script:
- membaca master identitas SPBU ESDM Semester I 2025;
- memakai koordinat kandidat yang sudah ada;
- mencoba geocoding alamat lainnya melalui Nominatim secara berurutan;
- menyimpan semua hasil (termasuk alamat yang gagal) di `data/spbu_geocode_candidates.csv`;
- membuat `data/stations_public_runnable.csv` dengan kolom yang diwajibkan `geofuel.data._read_stations`;
- membuat `data/fleet_scenario.csv` dengan kolom yang diwajibkan `_read_fleet`.

Parameter default operasional dibuat sebagai **skenario**, bukan observasi aktual: kapasitas tangki 30.000 L, stok awal 15% kapasitas, demand 8.000 L/hari, simpangan demand 15%, lead time 0,35 hari, dan armada 8.000/16.000/24.000 L. Ubah dengan `--capacity`, `--demand`, dan `--stock-fraction` bila ada dasar asumsi lain.

Untuk hanya memakai koordinat yang telah tersedia tanpa akses internet:

```powershell
python scripts/build_public_runnable_dataset.py --no-geocode
```

## 3. Validasi input

```powershell
python -c "from geofuel.data import _read_stations,_read_fleet; s=_read_stations('data/stations_public_runnable.csv'); f=_read_fleet('data/fleet_scenario.csv',1); print('OK:',len(s),'SPBU; fleet:',len(f[0]))"
```

Jika hasil geocoding hanya dua titik, maka eksperimen hanya mencakup dua titik itu. Jangan menyebutnya seluruh 27 SPBU. Buka `data/spbu_geocode_candidates.csv`, cek setiap kandidat di peta, dan perbaiki koordinat yang tidak tepat sebelum menjalankan rute.

## 4. Jalankan model dengan jaringan jalan OSM

Setelah koordinat terminal Fuel Terminal Ujung Berung di `.env` diverifikasi dan HiGHS tersedia:

```powershell
python experiment.py --n 0 --station-csv data/stations_public_runnable.csv --fleet-csv data/fleet_scenario.csv --reps 1
```

Jangan gunakan `--offline` untuk hasil penelitian rute karena opsi tersebut memakai grid jalan sintetis. Jika jaringan OSM gagal diunduh atau solver tidak tersedia, perbaiki dependensi/koneksi/konfigurasi; jangan menafsirkan fallback sebagai solusi MILP optimal.

## 5. Data yang memang tidak tersedia dari sumber publik

Dataset publik tidak memberi stok aktual, kapasitas tangki, penjualan harian per SPBU, lead time aktual, jumlah/kapsitas armada terminal, biaya aktual, maupun relasi pasok terminal ke masing-masing SPBU. Untuk mengganti asumsi skenario dengan data aktual, diperlukan data internal/izin observasi Pertamina. Jangan mengklaim output skenario sebagai data aktual.
