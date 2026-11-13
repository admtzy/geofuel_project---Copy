# Laporan validasi paket GEO-FUEL

Tanggal validasi: 11 November 2026.

## Pemeriksaan yang berhasil

- `python -m compileall -q geofuel experiment.py scripts tests`: berhasil.
- `python -m unittest discover -s tests -v`: 12 unit test berhasil, mencakup perhitungan inventory, statistik demand historis, validasi kelengkapan tanggal sales, waktu loading, kapasitas truk, stok terminal, dan stok akhir SPBU.
- `python scripts/check_data.py`: berhasil membaca 10 SPBU demo dan status enam armada demo.
- Simulasi M0 dan M1 menggunakan grid jalan sintetis: berhasil.
- `GET /api/health`, `GET /api/data-info`, dan `GET /` melalui FastAPI TestClient: HTTP 200.
- `POST /api/run` dan `POST /api/compare` pada mode offline melalui FastAPI TestClient: HTTP 200.
- Pemeriksaan parse JavaScript inline pada WebGIS: berhasil.
- Eksperimen offline terbatas `--n 6 --reps 1 --fleet-counts 2` berhasil menghasilkan `experiment_results.csv` dan `experiment_summary.csv`.

## Batas validasi lingkungan

- Lingkungan penyusunan paket tidak memiliki Pyomo, HiGHS/highspy, atau OSMnx dan tidak dapat mengakses internet untuk memasangnya.
- Karena itu, eksekusi solver MILP M2/M3 dengan HiGHS sungguhan belum dapat divalidasi di lingkungan ini. Di lingkungan tanpa solver, kode secara eksplisit menandai fallback M1; jangan menganggap fallback sebagai hasil MILP.
- Pengambilan jaringan OpenStreetMap aktual melalui OSMnx belum diuji di lingkungan ini. Pengujian API dan simulasi menggunakan graf `SIMULATED_GRID_OFFLINE`.
- Seluruh sepuluh SPBU demo dan enam armada demo berstatus `SIMULATED`; lokasi terminal bawaan berstatus `UNVERIFIED` dan stok terminal bawaan `SIMULATED`.

## Sebelum eksperimen penelitian

1. Instal `requirements.txt` di komputer pengguna.
2. Jalankan `python scripts/check_solver.py` dan pastikan `appsi_highs tersedia: True`.
3. Ganti master SPBU dan armada demo dengan data yang benar-benar diverifikasi.
4. Isi riwayat penjualan harian secara lengkap; catat hari tanpa penjualan sebagai nol.
5. Catat `stock_as_of` agar snapshot stok bisa ditelusuri.
6. Verifikasi koordinat terminal, SPBU, dan hubungan SPBU yang benar-benar dilayani terminal tersebut.
7. Jalankan tanpa mode offline dan pastikan response menunjukkan `OPENSTREETMAP_OSMNX`.
8. Catat sumber data, asumsi, seed eksperimen, skenario, dan status fallback saat melaporkan hasil.
