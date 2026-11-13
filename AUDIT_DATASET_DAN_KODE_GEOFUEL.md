# Audit kesesuaian dataset dan kode GEO-FUEL

Tanggal audit: 13 November 2026  
Dasar: `PENDAHULUAN IKMS (Dipulihkan).docx` dan ZIP proyek `Geoful(1).zip`.

## 1. Kesimpulan

Proyek sudah memiliki fondasi yang sesuai dengan metodologi GEO-FUEL: graf jalan, inventory intelligence, formulasi HFVRPTW, rolling-horizon simulation, API, dan WebGIS 2D. Namun, paket ini **belum merupakan eksperimen penelitian final** karena koordinat fasilitas, relasi terminal-SPBU, data operasi, dan solver belum seluruhnya tervalidasi.

Proposal memang memperbolehkan dua kelompok data: geospasial publik dan operasional sintetis. Karena itu, stok, demand, kapasitas tangki, armada, time windows, waktu bongkar, serta biaya boleh dibangkitkan untuk simulasi, tetapi harus berlabel `SIMULATED`/`ASSUMPTION`, bersumber/beralasan, dan diuji sensitivitas. Jangan menuliskannya sebagai data Pertamina aktual.

## 2. Temuan dataset saat audit

| File | Isi yang terverifikasi | Batasan |
|---|---|---|
| `data/spbu_kota_bandung_esdm_2025.csv` | 27 identitas SPBU Kota Bandung pada daftar ESDM Semester I 2025 | Bukan bukti bahwa seluruhnya dilayani Fuel Terminal Ujung Berung; koordinat mayoritas kosong |
| `data/spbu_geocode_candidates.csv` | 27 baris kandidat geocoding; hanya 2 memiliki koordinat | Kandidat peta/direktori harus dicek manual; geocoding nama/alamat bisa salah |
| `data/stations_public_runnable.csv` | 2 titik dengan koordinat kandidat dan parameter operasional | Hanya bisa menjalankan pilot 2 titik; stok, kapasitas, demand, lead time, time window adalah asumsi |
| `data/fleet_scenario.csv` | 6 baris armada skenario | Bukan armada aktual |
| `data/stations_demo.csv` | 10 titik simulasi | Bukan fasilitas aktual |
| `data/fleet_demo.csv` | 6 armada simulasi | Bukan armada aktual |
| `data/event_scenarios.csv` | Skenario permintaan/event | Pengali skenario, bukan pengamatan historis |
| `data/daily_sales_synthetic_demo.csv` | Penjualan sintetis untuk demo | Tidak boleh dipakai sebagai penjualan aktual |

Cakupan proposal menyebut 30 SPBU. Daftar ESDM yang digunakan di proyek ini berisi 27 SPBU Kota Bandung. Jangan menyamakan kedua angka tersebut: wilayah administrasi kota dan wilayah layanan terminal adalah dua hal berbeda. Jumlah fasilitas penelitian harus ditentukan dari daftar yang benar-benar terhubung ke terminal objek studi dan koordinatnya sudah diperiksa.

## 3. Kesesuaian implementasi dengan proposal

| Komponen proposal | Implementasi saat ini | Status |
|---|---|---|
| Geospatial Data Layer | OSMnx/NetworkX; CSV; graf offline sintetis untuk tes | Sebagian sesuai |
| Inventory Intelligence | DOI, safety stock, time-to-safety, kebutuhan kirim | Sesuai secara fungsi; input operasi sintetis |
| HFVRPTW | Pyomo + HiGHS, kapasitas armada, waktu, rute, shortage | Ada di kode; perlu uji solver nyata |
| Rolling-horizon | Re-optimasi berdasarkan stok dan posisi kendaraan simulasi setiap epoch | Simulasi; bukan optimasi dari GPS live |
| Traffic | Faktor waktu normal/padat/sangat padat pada OD | Sesuai skenario metodologi; bukan traffic real-time per ruas |
| WebGIS | Leaflet 2D | 2D ada; 3D belum ada |
| PostgreSQL/PostGIS | Belum terhubung; input CSV dan state in-memory | Belum sesuai tabel arsitektur proposal |
| GPS | API menerima posisi perangkat dan menyimpan posisi terbaru dalam memori | Tidak otomatis mengubah posisi kendaraan pada solver |
| Ekonomi | NPV, BCR, IRR, payback dengan CAPEX/OPEX ilustratif | Modul ada; hasil tergantung asumsi dan saving eksperimen |

Catatan penting: proposal membatasi klaim adaptif pada perubahan parameter simulasi bila GPS/traffic aktual tidak tersedia. Dengan batasan itu, rolling-horizon simulatif dapat dipertahankan, tetapi jangan menyebutnya sistem real-time operasional.

## 4. Perbaikan teknis pada paket audit

- `experiment.py` sekarang menerima `--station-csv` dan `--fleet-csv`, sehingga dataset tidak perlu disetel lewat environment variable untuk eksperimen batch.
- `scripts/check_data.py` sekarang menerima argumen `--station-csv` dan `--fleet-csv`.
- API menerima `n=0` sebagai pilihan memakai seluruh baris CSV.
- Output eksperimen menyimpan `experiment_metadata.json` untuk mencatat input, jumlah baris, mode jaringan, seed, dan skenario.
- Script pembentuk dataset mempertahankan label sumber koordinat dari master, bukan menyamakan seluruh kandidat sebagai Nominatim.

## 5. Perintah uji yang benar

Jalankan dari folder proyek `Geoful` di PowerShell.

### A. Instalasi

```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Jika Python 3.10 tidak tersedia, gunakan `py -3.11` dan konsisten memakai interpreter tersebut.

### B. Validasi struktur input pilot publik

```powershell
.\.venv\Scripts\python.exe scripts/check_data.py --station-csv data/stations_public_runnable.csv --fleet-csv data/fleet_scenario.csv
```

Output yang diharapkan saat ini: 2 SPBU, 6 armada skenario. Ini memeriksa struktur/angka, bukan memverifikasi posisi di lapangan.

### C. Periksa solver

```powershell
.\.venv\Scripts\python.exe scripts/check_solver.py
```

Syarat sebelum mengklaim M2/M3 sebagai MILP: output `appsi_highs tersedia: True`. Bila False, install ulang `pyomo` dan `highspy` pada interpreter `.venv` yang sama. Jangan melaporkan siklus fallback sebagai hasil MILP.

### D. Uji alur program tanpa internet

```powershell
.\.venv\Scripts\python.exe experiment.py --offline --n 0 --reps 1 --fleet-counts 2 --station-csv data/stations_public_runnable.csv --fleet-csv data/fleet_scenario.csv --output-dir results/test_public_offline
```

Mode `--offline` menggunakan grid buatan, bukan jalan Bandung. Hasil hanya smoke test alur program, bukan hasil spasial untuk paper.

### E. Uji dengan jaringan jalan OSM

```powershell
.\.venv\Scripts\python.exe experiment.py --n 0 --reps 1 --fleet-counts 2 --station-csv data/stations_public_runnable.csv --fleet-csv data/fleet_scenario.csv --output-dir results/test_public_osm
```

Perlu internet, OSMnx, dan koordinat terminal yang telah diverifikasi. Jangan lanjut jika koordinat terminal masih placeholder/perkiraan atau titik SPBU belum dicek.

### F. Menjalankan API/WebGIS

Atur `.env`:

```text
GEOFUEL_STATION_CSV=data/stations_public_runnable.csv
GEOFUEL_FLEET_CSV=data/fleet_scenario.csv
```

Kemudian:

```powershell
.\.venv\Scripts\python.exe -m uvicorn geofuel.api:app --host 127.0.0.1 --port 8000
```

Buka `http://127.0.0.1:8000`. Untuk API dengan semua baris CSV, kirim `n: 0` di body `/api/run`.

## 6. Urutan yang benar untuk membuat dataset penelitian

1. Tetapkan terminal objek studi dan verifikasi koordinatnya dari sumber resmi/otoritatif.
2. Dapatkan daftar SPBU yang benar-benar dilayani terminal. Daftar SPBU Kota Bandung saja belum membuktikan relasi pasok.
3. Cocokkan identitas SPBU dengan koordinat OSM/direktori, periksa tiap titik pada peta, simpan URL sumber, tanggal pemeriksaan, dan status verifikasi.
4. Hanya masukkan titik yang lolos pemeriksaan ke `stations_*.csv`.
5. Bentuk parameter sintetis untuk stok, demand, kapasitas, armada, time windows, dan biaya; simpan rentang/distribusi, random seed, dan alasan pemilihan parameter.
6. Uji rentang rendah/sedang/tinggi dan analisis sensitivitas. Pastikan skenario menghasilkan kondisi menantang (misalnya stok terminal terbatas, demand meningkat, kapasitas armada tidak cukup) agar KPI tidak selalu 100%.
7. Pastikan HiGHS menyelesaikan MILP dan catat status solver serta gap/waktu. Jika fallback aktif, pisahkan dari hasil optimasi.
8. Jalankan eksperimen dengan OSM nyata, bukan grid offline.
9. Baru kemudian bandingkan M0-M3, KPI operasional, dan proyeksi ekonomi.

## 7. Batas klaim

Dengan paket sekarang, klaim yang aman adalah: “prototipe GEO-FUEL diuji melalui simulasi menggunakan dua titik lokasi SPBU kandidat, jaringan grid offline untuk pengujian alur atau OSM setelah verifikasi, serta parameter operasional sintetis.”

Belum aman untuk mengklaim: “sistem diuji pada 30 SPBU layanan Fuel Terminal Ujung Berung dengan stok, demand, armada, dan kemacetan aktual” atau “M2/M3 telah menghasilkan solusi MILP” sebelum semua prasyarat di atas terpenuhi.
