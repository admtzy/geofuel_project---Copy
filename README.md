# GEO-FUEL — Prototipe Geospatial Decision Support System

GEO-FUEL adalah prototipe **sistem pendukung keputusan distribusi BBM dari satu Fuel Terminal ke beberapa SPBU**. Sistem menggabungkan perhitungan persediaan, jaringan jalan, alokasi mobil tangki, optimasi rute HFVRPTW, simulasi perubahan stok, dan visualisasi WebGIS.

> **Penting tentang kebenaran data:** file `stations_demo.csv` dan `fleet_demo.csv` adalah data **SIMULATED**. Koordinat terminal bawaan juga berstatus **UNVERIFIED**. Jangan menyebut lokasi, stok, demand, armada, biaya, atau hasil demo sebagai kondisi operasional aktual Pertamina. Semua asumsi harus diganti atau divalidasi sebelum menjadi hasil penelitian.

## 1. Apa yang sistem hasilkan?

Untuk satu periode simulasi, GEO-FUEL menghitung:

1. SPBU yang perlu dipasok lebih cepat dan alasannya.
2. Jumlah liter yang direkomendasikan untuk setiap SPBU.
3. Mobil tangki yang dialokasikan dan kapasitas yang digunakan.
4. Urutan kunjungan dari terminal ke SPBU lalu kembali ke terminal.
5. Perkiraan jarak, waktu tempuh, waktu pelayanan, dan keterlambatan.
6. Biaya simulasi, volume tidak terpenuhi/stockout, service level, dan utilisasi armada.
7. Perubahan keputusan setiap siklus rolling horizon.

Model ini menangani **satu jenis produk BBM untuk setiap run**. Kompartemen mobil tangki multi-produk, pasokan masuk dari kilang ke terminal, dan sistem GPS operasional belum dimodelkan.

## 2. Bagaimana sistem tahu SPBU perlu diisi?

Sistem tidak menentukan urgensi hanya dari jarak. Sistem membutuhkan empat informasi utama:

- stok sekarang di tangki SPBU (`initial_stock_liters`, lalu berubah selama simulasi);
- konsumsi harian SPBU (`daily_demand_liters`), idealnya dihitung dari penjualan harian historis;
- safety stock, yaitu stok pengaman untuk menghadapi variasi permintaan dan lead time;
- waktu yang dibutuhkan kendaraan untuk loading, perjalanan, dan bongkar BBM.

### 2.1 Days of Inventory (DOI)

\[
DOI_i = \frac{I_i}{d_i}
\]

`I_i` adalah stok SPBU dalam liter dan `d_i` adalah konsumsi liter per hari. DOI menyatakan berapa hari stok dapat bertahan pada laju konsumsi tersebut. Stok 4.000 liter dengan demand 10.000 liter/hari memiliki DOI 0,4 hari.

### 2.2 Safety stock (SS)

Rumus mengikuti bentuk persamaan pada dokumen penelitian:

\[
SS_i = z\sqrt{L_i\sigma_{d,i}^{2}+d_i^{2}\sigma_{L,i}^{2}}
\]

- `z`: faktor tingkat pelayanan.
- `L`: rata-rata lead time dalam hari.
- `sigma_d`: simpangan baku demand harian dalam liter/hari.
- `d`: rata-rata demand harian.
- `sigma_L`: simpangan baku lead time dalam hari.

Jika tersedia, kode memakai `demand_std_liters_per_day`, `mean_lead_time_days`, dan `lead_time_std_days` dari CSV. Jika kolom statistik kosong, kode memakai asumsi default: `z=1.65`, `mean_lead_time_days=0.35`, `demand_std=20% dari demand`, dan `lead_time_std_days=0.10`. Nilai default bukan standar resmi Pertamina; kalibrasi dengan riwayat operasi diperlukan.

### 2.3 Waktu sampai safety stock

\[
T_{risk,i}=\frac{I_i-SS_i}{d_i}\times24
\]

Hasilnya dalam jam. Nilai negatif berarti stok saat ini sudah berada di bawah safety stock.

### 2.4 Lead time pengiriman

Dalam prototipe:

`effective_lead = loading + perjalanan terminal-SPBU + bongkar muat`

Waktu bongkar dihitung dari waktu dasar ditambah volume pengiriman dibagi laju bongkar. Perjalanan berasal dari jaringan jalan dan faktor traffic skenario.

### 2.5 Aturan pemicu dan kategori prioritas

SPBU menjadi kandidat pengiriman apabila:

```text
stok_sekarang <= safety_stock
ATAU
time_to_safety <= effective_lead + priority_buffer
```

`priority_buffer` bawaan 2 jam dan harus diuji sensitivitasnya.

| Status | Arti |
|---|---|
| KRITIS | Stok sudah menyentuh atau berada di bawah safety stock |
| TINGGI | Stok diperkirakan menyentuh safety stock sebelum pengiriman selesai |
| SEDANG | Stok diperkirakan menyentuh safety stock dalam lead time + buffer |
| AMAN | Belum melewati ambang pemesanan ulang |

Bentuk ekuivalennya adalah titik pemesanan ulang:

\[
ROP_i = \min(C_i, SS_i + d_i\times\frac{effective\_lead+buffer}{24})
\]

Jika stok saat ini berada di bawah ROP, sistem mulai meminta pengiriman. Kategori prioritas tetap membedakan apakah stok sudah kritis, akan kritis sebelum pengiriman, atau masih dalam buffer.

### 2.6 Contoh angka

Misalkan satu SPBU memiliki:

- kapasitas tangki 30.000 liter;
- stok sekarang 4.000 liter;
- konsumsi 10.000 liter/hari;
- jarak waktu perjalanan dari terminal 1 jam;
- loading 0,25 jam;
- parameter default safety stock dan buffer 2 jam.

Perhitungan kode menghasilkan kira-kira:

| Indikator | Hasil |
|---|---:|
| DOI | 0,40 hari |
| Safety stock | 2.556 liter |
| Waktu sampai safety stock | 3,47 jam |
| Loading + perjalanan | 1,25 jam |
| Lead time efektif termasuk bongkar | 1,95 jam |
| Reorder point | 4.202 liter |
| Volume menuju target isi 85% saat tiba | 22.021 liter |
| Prioritas | SEDANG |

Mengapa SEDANG? Stok 4.000 liter masih lebih besar dari safety stock 2.556 liter, tetapi diperkirakan menyentuh safety stock dalam 3,47 jam. Lead time efektif + buffer adalah sekitar 3,95 jam. Karena 3,47 <= 3,95, SPBU masuk daftar pengiriman.

Ini menjawab "dari mana sistem tahu SPBU butuh cepat": dari kombinasi **stok, laju konsumsi, variasi demand, waktu pasok, dan safety stock**. Jika stok dan demand aktual tidak tersedia, sistem hanya dapat memberikan hasil simulasi, bukan mengetahui kebutuhan nyata SPBU.

### 2.7 Bagaimana volume pengiriman dihitung?

Stok diproyeksikan sampai kendaraan tiba:

\[
I_{arrival}=\max(0,I_{now}-d\times\frac{lead_{arrival}}{24})
\]

Target isi demo adalah 85% kapasitas tangki. Volume dikirim:

\[
q_i=\min(C_i-I_{arrival},\;0.85C_i-I_{arrival})
\]

Volume tidak boleh melebihi ruang kosong tangki atau kebutuhan menuju target. Target 85% adalah asumsi eksperimen, bukan ketentuan resmi. Model dapat mengirim parsial jika kapasitas mobil tangki atau stok terminal tidak cukup.

## 3. Sumber data yang harus disiapkan

### 3.1 Data terminal

- nama dan koordinat terminal yang sudah diverifikasi;
- stok BBM awal terminal untuk produk yang sedang dianalisis;
- status sumber data terminal.

Atur melalui `.env`:

```text
GEOFUEL_TERMINAL_NAME=Nama terminal yang diverifikasi
GEOFUEL_TERMINAL_LAT=-6.xxxxxx
GEOFUEL_TERMINAL_LON=107.xxxxxx
GEOFUEL_TERMINAL_INITIAL_STOCK_LITERS=180000
GEOFUEL_TERMINAL_DATA_STATUS=ACTUAL_VERIFIED
GEOFUEL_TERMINAL_STOCK_STATUS=ACTUAL_VERIFIED
```

Angka `180000` di atas hanya contoh. Ganti dengan stok terminal aktual atau nyatakan sebagai `SIMULATED`.

### 3.2 Master SPBU

Gunakan `data/station_master_template.csv` sebagai template identitas dan kondisi fasilitas. Isi hanya SPBU yang benar-benar dilayani terminal objek penelitian. Kolom penting:

| Kolom | Keterangan |
|---|---|
| `station_id` | ID unik SPBU |
| `name`, `address` | Identitas dan alamat |
| `lat`, `lon` | Koordinat decimal degree yang diverifikasi |
| `capacity_liters` | Kapasitas tangki untuk satu produk BBM |
| `initial_stock_liters` | Stok pada waktu mulai simulasi |
| `stock_as_of` | Waktu pengukuran stok (metadata untuk memastikan snapshot stok tidak kedaluwarsa) |
| `window_start`, `window_end` | Waktu penerimaan, format jam desimal 0–24 |
| `mean_lead_time_days` | Rata-rata lead time pasokan |
| `lead_time_std_days` | Simpangan baku lead time |
| `service_level_z` | Faktor tingkat pelayanan |
| `data_status` | `ACTUAL_VERIFIED`, `SIMULATED`, atau `UNVERIFIED` |
| `source`, `verified_at` | Jejak sumber dan tanggal verifikasi |

Alamat saja belum cukup. Koordinat harus dicek posisinya. Kode melakukan snap koordinat ke node jalan terdekat dan menolak titik yang lebih jauh dari batas `GEOFUEL_MAX_SNAP_DISTANCE_M` (default 1.500 meter).

### 3.3 Riwayat penjualan harian untuk demand

Gunakan `data/daily_sales_history_template.csv` dengan kolom:

```csv
station_id,date,sales_liters
SPBU001,2026-10-01,12000
SPBU001,2026-10-02,11500
```

Contoh di atas hanya format. Ganti dengan penjualan yang benar. Masukkan satu observasi untuk setiap SPBU setiap tanggal. Jika tidak ada penjualan pada hari tersebut, catat `0`; jangan menghilangkan tanggal karena akan dianggap data hilang.

Disarankan minimal 14 hari dan lebih baik 30–90 hari atau lebih, dengan periode yang representatif. Untuk perhitungan yang benar, data perlu mencakup seluruh hari pengamatan; hari tanpa transaksi dicatat sebagai nol, sedangkan hari yang tidak diketahui harus dibiarkan sebagai data hilang dan diselidiki. Jalankan:

```powershell
python scripts/prepare_actual_stations.py --master data/station_master_actual.csv --sales data/daily_sales_actual.csv --output data/stations_actual.csv --min-days 14
```

Script menggabungkan master SPBU dengan rata-rata penjualan harian dan simpangan baku penjualan harian. Script **tidak** mengubah `data_status` menjadi `ACTUAL_VERIFIED`; verifikasi tetap tanggung jawab peneliti.

Untuk mendapatkan `mean_lead_time_days` dan `lead_time_std_days`, gunakan riwayat waktu dari pesanan/pengajuan pasokan sampai BBM diterima SPBU. Jika belum ada, nilai default masih asumsi.

### 3.4 Data armada

Gunakan `data/fleet_template.csv`:

| Kolom | Keterangan |
|---|---|
| `vehicle_id` | ID mobil tangki |
| `capacity_liters` | Kapasitas angkut |
| `data_status` | Status data armada |

Satu baris mewakili satu kendaraan. Kapasitas dan jumlah kendaraan harus sesuai armada yang benar-benar tersedia apabila ingin menyebut hasil sebagai aktual.

### 3.5 Jaringan jalan dan kemacetan

OSMnx mengambil struktur jaringan jalan OpenStreetMap dan membentuk graf. NetworkX menghitung jarak dan waktu jaringan. Ini bukan sumber kecepatan lalu lintas aktual.

Saat ini kemacetan dibentuk sebagai skenario sintetis:

- Normal: faktor dasar 1,00.
- Padat: faktor dasar 1,35.
- Sangat padat: faktor dasar 1,80.
- Profil jam sibuk pagi dan sore menambah faktor waktu.

Faktor tersebut diterapkan pada waktu perjalanan OD di simulasi. Jalur geometri yang ditampilkan tetap berasal dari lintasan jaringan berbobot panjang terpendek; M3 mengubah estimasi waktu OD untuk perencanaan, bukan mencari ulang jalur alternatif per ruas akibat traffic aktual. Kode belum membaca kecepatan aktual per ruas, belum memanfaatkan GPS live, dan belum memilih alternatif jalan per ruas berdasarkan traffic live. Jadi hasilnya harus disebut **simulasi skenario traffic**, bukan prediksi traffic real-time Bandung. Indeks kemacetan agregat satu kota tidak cukup untuk mengetahui waktu tempuh tiap ruas.

## 4. Metode pembanding M0–M3

| Metode | Mekanisme |
|---|---|
| M0 | Heuristik yang memilih SPBU berdasarkan jarak terdekat, dengan batas kapasitas truk dan stok terminal |
| M1 | Heuristik yang memilih SPBU berdasarkan waktu paling dekat ke safety stock, lalu mengurutkan kunjungan dengan nearest-neighbour |
| M2 | Pyomo + HiGHS HFVRPTW, merencanakan dengan waktu perjalanan free-flow |
| M3 | Pyomo + HiGHS HFVRPTW, memasukkan faktor traffic skenario ke estimasi waktu saat perencanaan |

Semua metode menggunakan kondisi traffic skenario saat perjalanan dieksekusi. M2/M3 adalah metode MILP hanya jika Pyomo dan HiGHS benar-benar tersedia dan solver mengembalikan solusi yang dapat dibaca. Jika tidak, kode melakukan fallback ke M1 dan mencatat `fallback_used=true`. Jangan melaporkan siklus fallback sebagai hasil MILP.

Kendala MILP meliputi kapasitas setiap mobil tangki, total stok terminal, maksimal satu kendaraan per SPBU dalam satu siklus, jendela waktu pelayanan, keberangkatan/kepulangan terminal, keseimbangan aliran, dan eliminasi subtour. Pengiriman parsial dan volume tidak terpenuhi direpresentasikan oleh variabel `q` dan `u`.

## 5. Struktur proyek

```text
GEOFUEL_FULL/
├── geofuel/
│   ├── config.py          # nilai konfigurasi dan asumsi simulasi
│   ├── data.py            # CSV, graf OSMnx/grid, matriks jarak/waktu
│   ├── inventory.py       # DOI, safety stock, urgensi, kebutuhan liter
│   ├── model.py           # formulasi MILP HFVRPTW dengan Pyomo
│   ├── simulation.py      # eksekusi armada, stok, rolling horizon, KPI
│   ├── economics.py       # NPV, BCR, IRR, payback period
│   ├── api.py             # FastAPI dan keluaran JSON
│   └── static/index.html  # Leaflet WebGIS
├── data/
│   ├── stations_demo.csv
│   ├── fleet_demo.csv
│   ├── spbu_template.csv
│   ├── fleet_template.csv
│   ├── station_master_template.csv
│   └── daily_sales_history_template.csv
├── scripts/
│   ├── check_data.py
│   └── prepare_actual_stations.py
├── tests/test_inventory.py
├── experiment.py
├── requirements.txt
├── requirements-minimal.txt
├── .env.example
└── README.md
```

## 6. Instalasi dan menjalankan di Windows 10/11

Disarankan Python 3.10 atau 3.11. Buka PowerShell di folder `GEOFUEL_FULL`.

```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Jika aktivasi PowerShell diblokir:

```powershell
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Salin `.env.example` menjadi `.env`, lalu periksa koordinat dan stok terminal. Jalankan API:

```powershell
python -m uvicorn geofuel.api:app --host 127.0.0.1 --port 8000 --reload
```

Buka:

- WebGIS: `http://127.0.0.1:8000`
- Dokumentasi API: `http://127.0.0.1:8000/docs`
- Health check: `http://127.0.0.1:8000/api/health`
- Info data: `http://127.0.0.1:8000/api/data-info`

Untuk menggunakan file aktual, tambahkan ke `.env`:

```text
GEOFUEL_STATION_CSV=data/stations_actual.csv
GEOFUEL_FLEET_CSV=data/fleet_actual.csv
```

Jalankan validasi CSV:

```powershell
python scripts/check_data.py
```

### Mode offline untuk mencoba antarmuka

```powershell
pip install -r requirements-minimal.txt
python -m uvicorn geofuel.api:app --reload
```

Pada WebGIS, centang **Gunakan grid jalan SIMULATED (offline)**. Grid tersebut hanya untuk mengetes alur program, bukan jaringan jalan Bandung. Tile peta Leaflet tetap memerlukan koneksi internet. Untuk M2/M3, instal Pyomo dan HiGHS:

```powershell
pip install pyomo highspy
python -c "import pyomo.environ as pyo; s=pyo.SolverFactory('appsi_highs'); print('HiGHS tersedia:', s.available())"
```

Jika solver tidak tersedia, M2/M3 berjalan dengan fallback M1 dan UI/API menandainya. Untuk jaringan OSM, instalasi penuh memerlukan OSMnx serta akses internet saat graf diunduh.

## 7. Eksperimen M0–M3

Eksperimen kecil offline:

```powershell
python experiment.py --offline --n 10 --reps 1 --solver-time-limit 5
```

Dengan jaringan OSMnx:

```powershell
python experiment.py --n 10 --reps 2 --solver-time-limit 10
```

Mengubah jumlah armada dan replikasi:

```powershell
python experiment.py --offline --n 10 --reps 3 --fleet-counts 2,3,4,5 --solver-time-limit 8
```

Output disimpan ke `results/experiment_results.csv` dan `results/experiment_summary.csv`. Gunakan seed, input, dan skenario yang sama untuk membandingkan metode. Laporkan juga jumlah siklus fallback dan sumber graf yang dipakai.

## 8. Batasan prototipe yang harus ditulis jujur dalam laporan

1. Demo memakai data sintetis; data aktual hanya boleh diklaim setelah diverifikasi.
2. `initial_stock_liters` harus merupakan snapshot stok pada waktu mulai perencanaan. Catat waktu pengukuran pada `stock_as_of`; tanpa data stok terbaru, sistem tidak bisa mengetahui kebutuhan aktual SPBU.
3. Koordinat terminal default adalah perkiraan dan harus diganti.
4. Lalu lintas adalah skenario faktor pengali, bukan kecepatan aktual setiap ruas.
5. Rute jalan antarfasilitas saat ini dibentuk dari lintasan jaringan berbobot panjang; M3 mengubah estimasi waktu OD, bukan melakukan rerouting berdasarkan traffic aktual per ruas.
6. Sistem memodelkan satu produk BBM per run dan satu terminal; belum mengoptimalkan rantai pasok hulu, pasokan masuk terminal, multi-kompartemen, atau multi-produk.
7. Posisi mobil tangki adalah posisi simulasi dari rute, bukan GPS kendaraan nyata.
8. Parameter biaya, target isi 85%, buffer 2 jam, waktu loading/unloading, dan default statistik persediaan adalah asumsi yang harus diuji sensitivitasnya.
9. PostgreSQL/PostGIS, GeoPandas, QGIS, dan MapLibre belum menjadi dependensi inti kode ini. Penyimpanan input masih berbasis CSV dan graf di-cache di memori proses; QGIS dapat dipakai sebagai alat validasi manual.
10. Biaya waktu pada simulasi menghitung loading, perjalanan, dan bongkar muat. Waktu menunggu sebelum jendela penerimaan belum dipisahkan sebagai komponen biaya tenaga kerja tersendiri.

## 9. Pengujian

```powershell
python -m unittest discover -s tests -v
```

Pastikan semua tes lulus. Untuk M2/M3, pastikan solver tersedia dan `fallback_used` bernilai `false` pada siklus yang ingin dilaporkan sebagai hasil MILP.

## 8. GPS Android (opsional)

Server menyediakan endpoint penerimaan GPS kendaraan. Ikuti `GPS_ANDROID.md` untuk mengirim posisi dari Android melalui jaringan Wi-Fi yang sama. Endpoint `GET /api/gps/positions` menampilkan posisi terbaru per kendaraan. Fitur GPS ini tidak otomatis menjadikan stok, demand, traffic, atau hasil optimasi sebagai data real-time; sumber-sumber tersebut tetap mengikuti status data masing-masing.

## 9. Menjalankan di Windows

Ekstrak ZIP, buka folder `GEOFUEL_FULL231`, lalu klik dua kali `run_windows.bat`. Alternatif PowerShell:

```powershell
py -3.10 -m venv .venv
.venv\\Scripts\\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python -m uvicorn geofuel.api:app --host 0.0.0.0 --port 8000
```

Buka `http://127.0.0.1:8000`. Untuk penggunaan satu laptop saja, `127.0.0.1` juga cukup; gunakan `0.0.0.0` hanya jika perlu menerima GPS dari Android di jaringan lokal. Pastikan firewall mengizinkan koneksi privat.

## Pembaruan data Bandung, event demand, dan cakupan SPBU

- Impor titik SPBU OSM: `python scripts/import_spbu_osm.py --region kota-bandung`
  atau `--region bandung-raya`. Output CSV dan XLSX ada di `data/`.
- Hasil OSM adalah lokasi kandidat (`OSM_LOCATION_ONLY`), bukan data operasional
  terverifikasi. Lengkapi kapasitas, stok awal, demand harian, waktu layanan,
  parameter lead time, dan verifikasi terminal sebelum dipakai untuk keputusan.
- Pakai seluruh baris CSV dengan `python experiment.py --n 0`; angka default
  10 tetap untuk kompatibilitas.
- Uji lonjakan permintaan dengan `--event-factor 1.12` (contoh skenario Ramadan)
  atau `1.25` (contoh skenario puncak mudik). Ini pengali skenario, bukan hasil
  prediksi SPBU Bandung. Kalibrasikan dari histori penjualan lokal.
- OSM menyediakan jaringan jalan, bukan kecepatan lalu lintas real-time. Waze
  for Cities gratis bagi mitra yang disetujui; ATCS Bandung menyediakan CCTV,
  bukan API speed publik yang terkonfirmasi. Tanpa feed resmi/GPS armada, M3
  tetap merupakan skenario lalu lintas sintetis.


## Audit dan penggunaan dataset publik kandidat

Baca `AUDIT_DATASET_DAN_KODE_GEOFUEL.md` sebelum menjalankan eksperimen. File tersebut mencocokkan proposal dengan implementasi, menjelaskan status sumber data, serta memberikan urutan pengujian yang aman.

Eksperimen kini dapat menerima CSV secara langsung:

```powershell
python scripts/check_data.py --station-csv data/stations_public_runnable.csv --fleet-csv data/fleet_scenario.csv
python experiment.py --offline --n 0 --reps 1 --fleet-counts 2 --station-csv data/stations_public_runnable.csv --fleet-csv data/fleet_scenario.csv
```

Perintah di atas hanya menguji alur program pada dua titik koordinat kandidat dan grid offline sintetis. Untuk eksperimen spasial, verifikasi koordinat terminal dan SPBU, lalu jalankan tanpa `--offline` dengan OSMnx aktif. M2/M3 hanya boleh disebut MILP apabila `scripts/check_solver.py` menyatakan HiGHS tersedia dan tidak ada fallback.
