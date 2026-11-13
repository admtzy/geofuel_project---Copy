# Audit GEO-FUEL terhadap dokumen PENDAHULUAN IKMS

Audit paket sumber `Geoful.zip` dan dokumen proposal yang diberikan. Status data dan kode dibedakan agar hasil tidak melampaui bukti.

## 1. Kesesuaian modul dengan metode

| Kebutuhan pada dokumen | Implementasi paket | Status / catatan |
|---|---|---|
| Geospatial Data Layer: koordinat, jalan, jarak/waktu | `geofuel/data.py`, OSMnx, NetworkX | Ada. Terminal bawaan masih UNVERIFIED; jaringan OSM adalah struktur jalan, bukan traffic live. |
| Inventory Intelligence: DOI, safety stock, time-to-safety, kebutuhan, urgensi | `geofuel/inventory.py` dan `data.py` | Ada. Jika sales history tidak ada, sigma demand memakai asumsi 20%; pilot ini memakai data operasi SIMULATED. |
| HFVRPTW heterogenous fleet dengan Pyomo/HiGHS | `geofuel/model.py` | Formulasi ada: kapasitas truk, stok terminal, time windows, keterlambatan, subtour, pengiriman tidak terpenuhi. Solver wajib tersedia untuk klaim MILP. |
| M0 nearest-distance dan M1 stock urgency | `geofuel/simulation.py` | Ada sebagai heuristik pembanding. |
| M2 free-flow MILP dan M3 traffic-scenario MILP | `geofuel/simulation.py`, `model.py` | Ada. M3 mengalikan waktu OD dengan faktor skenario; belum menghitung traffic aktual per ruas atau memilih ulang jalur per segmen. |
| Rolling-horizon re-optimization | `geofuel/simulation.py` | Ada dalam simulasi tiap epoch; rute kendaraan yang sedang berjalan tidak diubah mendadak. |
| GPS armada aktual | `geofuel/api.py` menerima POST GPS | Endpoint penerima tersedia, tetapi posisi GPS belum menjadi state yang mengubah perhitungan rute/simulasi. Adaptasi saat ini berbasis state simulasi. |
| PostgreSQL/PostGIS | Tidak ditemukan koneksi/migrasi/query DB di paket | Belum diimplementasikan; input utama CSV dan memori. Jangan tulis bahwa prototipe sudah memakai PostGIS. |
| FastAPI | `geofuel/api.py` | Ada. |
| WebGIS 2D | `geofuel/static/index.html` memakai Leaflet | Ada. |
| WebGIS 3D | Tidak ditemukan engine 3D | Belum diimplementasikan. Ubah klaim dokumen menjadi pengembangan lanjutan atau tambahkan modul 3D. |
| CAPEX/OPEX, NPV, BCR, IRR, PP | `geofuel/economics.py` | Kalkulator proyeksi ada, tetapi seluruh default investasi/biaya adalah asumsi ilustratif. |

## 2. Data yang ditemukan dalam ZIP awal

- `stations_demo.csv`: 10 baris SPBU sintetis dengan koordinat sintetis.
- `fleet_demo.csv`: 6 kendaraan sintetis.
- `daily_sales_history_template.csv`: hanya header; memang template, bukan histori aktual.
- `station_master_template.csv` dan `spbu_template.csv`: template/contoh, bukan data aktual.
- `event_calendar_template.csv`: berisi faktor asumsi dengan kalender tahun 2026; bukan data permintaan aktual.
- `results/experiment_results.csv`: 108 baris, yaitu 27 kombinasi demand x traffic x fleet dikalikan 4 metode. Hasil lama berasal dari 10 SPBU demo dan tidak boleh dianggap hasil dengan daftar SPBU publik yang baru.

## 3. Dataset yang ditambahkan

- `data/spbu_kota_bandung_esdm_2025.csv`: 27 identitas SPBU Kota Bandung yang tercatat beroperasi pada daftar ESDM Semester I 2025. Kolom koordinat sengaja belum diisi untuk fasilitas yang belum memiliki pasangan koordinat terverifikasi.
- `data/stations_demo.csv`: pilot empat titik lokasi publik (kode 3440601, 3440602, 3440603, 3440606). Koordinat berasal dari listing OSM/PetaBBM; tiga kode 3440601-03 tidak muncul pada ekstrak ESDM Semester I 2025 sehingga identitas/status aktifnya belum dibuktikan oleh sumber resmi terbaru. Hanya 3440606 yang cocok dengan entri ESDM 2025. Kapasitas, stok, demand, dan parameter lead time adalah SIMULATED.
- `data/daily_sales_synthetic_demo.csv`: 30 hari penjualan sintetis untuk empat pilot; bukan penjualan aktual.
- `data/fleet_demo.csv` / `fleet_template.csv`: enam kapasitas armada heterogen dengan status SIMULATED.
- `data/event_scenarios.csv`: faktor event sebagai asumsi eksperimen tanpa tanggal kalender yang kedaluwarsa.
- `scripts/geocode_official_spbu.py`: geocoding alamat master dengan Nominatim satu request per detik. Output hanya kandidat koordinat.
- `scripts/build_synthetic_operational_data.py`: membangun CSV operasional sintetis lengkap setelah koordinat kandidat tersedia.

## 4. Batas interpretasi data

Daftar ESDM mengonfirmasi identitas/status SPBU pada Semester I 2025, bukan hubungan layanan dari Fuel Terminal Ujung Berung. Lokasi dari OpenStreetMap/PetaBBM tidak membuktikan bahwa SPBU aktif atau dilayani terminal tertentu. Kapasitas tangki, stok, penjualan, waktu tunggu, fleet, biaya dan demand yang tidak tersedia secara publik tidak boleh diperlakukan sebagai aktual; pada data pilot semuanya berlabel SIMULATED.

## 5. Ketidaksesuaian penting untuk laporan

1. Dokumen menyebut sekitar 30 SPBU, tetapi data publik ESDM yang dipakai pada master Kota Bandung berisi 27 entri aktif pada Semester I 2025. Jangan menyebut 27 ini sebagai 27 SPBU yang pasti dilayani Ujung Berung tanpa bukti relasi terminal.
2. Dokumen menyebut PostgreSQL/PostGIS, sedangkan paket saat ini belum mengimplementasikannya.
3. Dokumen menyebut visualisasi 2D/3D, sedangkan kode saat ini hanya Leaflet 2D.
4. Dokumen menyebut posisi GPS; API menerima update GPS, tetapi simulasi/optimizer belum menggunakan posisi tersebut untuk mengunci atau menghitung ulang rute.
5. Dokumen menyebut kondisi lalu lintas aktual; kode saat ini hanya traffic factor skenario normal/padat/sangat padat. Ini sesuai batasan di bagian metode yang menyatakan tidak ada traffic live, tetapi frasa “aktual” di bagian pendahuluan perlu disesuaikan agar tidak kontradiktif.
6. Status solver harus dilaporkan. `OPTIMAL` hanya bila solver menyatakan optimal; `FEASIBLE_INCUMBENT` bukan optimum global; fallback M1 bukan hasil MILP. Kode sekarang menyimpan klasifikasi solusi di log epoch.
7. Hasil eksperimen lama yang 108 baris harus diarsipkan sebagai hasil demo 10 SPBU. Jalankan ulang setelah data dan solver tervalidasi.

## 6. Eksperimen 27 skenario

Default `experiment.py` membentuk 3 level permintaan x 3 level traffic x 3 jumlah armada = 27 kombinasi skenario. Karena setiap kombinasi diuji dengan empat metode (M0-M3), total eksekusi metode adalah 108 untuk satu replikasi. File output:

- `results/experiment_results.csv`: seluruh eksekusi metode.
- `results/experiment_summary.csv`: rata-rata per metode.
- `results/experiment_by_scenario.csv`: hasil per skenario dan metode.

Untuk 27 kombinasi pada seluruh baris CSV: `python experiment.py --n 0 --reps 1 --event-id BASELINE`. Faktor event dibaca dari `data/event_scenarios.csv`; uji mudik misalnya memakai `--event-id MUDIK`.
