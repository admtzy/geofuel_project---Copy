# Data GEO-FUEL

## Data demo

- `stations_demo.csv`: 10 titik SPBU simulasi dengan lokasi, stok, konsumsi, kapasitas, dan jam penerimaan sintetis.
- `fleet_demo.csv`: 6 mobil tangki simulasi dengan kapasitas contoh.
- `station_master_template.csv`: template identitas, koordinat, kapasitas, snapshot stok, dan jam penerimaan SPBU.
- `daily_sales_history_template.csv`: template riwayat penjualan harian untuk menghitung demand.
- `spbu_template.csv`: contoh bentuk CSV input akhir setelah demand disiapkan.
- `fleet_template.csv`: template armada.

Tidak ada baris pada file demo yang mewakili SPBU atau kendaraan operasional Pertamina yang telah diverifikasi.

## Data aktual yang perlu diperoleh

1. Daftar SPBU yang benar-benar dilayani terminal penelitian, bukan seluruh SPBU di suatu kota secara otomatis.
2. Identitas/nama dan alamat fasilitas.
3. Koordinat yang telah dicek pada peta dan sumber resmi.
4. Kapasitas tangki untuk produk BBM yang dianalisis.
5. Stok awal pada waktu pengamatan, disertai timestamp `stock_as_of` agar jelas kapan stok diukur.
6. Konsumsi atau penjualan harian.
7. Waktu penerimaan dan waktu bongkar.
8. Kapasitas dan ketersediaan mobil tangki.
9. Parameter biaya aktual atau asumsi yang memiliki dasar dan diuji sensitivitas.

Relasi terminal-ke-SPBU (SPBU mana dilayani terminal tertentu) tidak dapat disimpulkan hanya dari OpenStreetMap. Relasi tersebut perlu dikonfirmasi melalui sumber operasional yang dapat dipertanggungjawabkan. Jika tidak tersedia, nyatakan keterbatasannya dan gunakan skenario simulasi secara transparan.

## Penandaan

- `SIMULATED`: dibentuk untuk eksperimen, bukan hasil pengukuran fasilitas.
- `UNVERIFIED`: data sudah dimasukkan tetapi belum diverifikasi.
- `ACTUAL_VERIFIED`: hanya dipakai bila sumber dan proses verifikasinya terdokumentasi.

`stock_as_of` harus menunjukkan waktu snapshot stok. Jangan menggunakan stok yang sudah kedaluwarsa seolah-olah merupakan stok saat ini. `data_status` bukan bukti otomatis; peneliti harus menyimpan sumber, tanggal verifikasi, dan bukti pengukuran.

## Mengimpor lokasi SPBU Bandung dari OpenStreetMap

Jalankan `python scripts/import_spbu_osm.py --region kota-bandung` atau
`--region bandung-raya`. Script mengambil objek `amenity=fuel` melalui Overpass
API dan menghasilkan CSV serta XLSX bila `openpyxl` terpasang. Hasil berstatus
`OSM_LOCATION_ONLY`: ini hanya inventaris lokasi, bukan konfirmasi SPBU aktif,
bukan data stok, kapasitas, penjualan, atau relasi terminal. Verifikasi titik
secara manual dan lengkapi kolom operasional sebelum simulasi. Berikan atribusi
© OpenStreetMap contributors, ODbL 1.0.

Untuk memakai semua SPBU dalam CSV: `python experiment.py --n 0`. Default `--n 10`
tetap dipertahankan agar perilaku prototipe lama tidak berubah. Contoh uji
lonjakan permintaan: `python experiment.py --n 0 --event-factor 1.12`.
Pengali event adalah skenario simulasi seragam, bukan ramalan aktual per SPBU.
Template kalender ada di `event_calendar_template.csv`; tanggal perlu diperbarui
sesuai kalender resmi setiap tahun.

## Traffic gratis

Peta jalan OSM dan waktu tempuh free-flow dapat diunduh tanpa biaya lisensi API,
tetapi bukan traffic real-time. Bandung ATCS dapat menjadi sumber CCTV publik
untuk observasi/estimasi manual atau computer vision jika akses dan ketentuan
stream mengizinkan; jangan menganggapnya sebagai API kecepatan jalan. Waze for
Cities menyediakan feed tanpa biaya untuk mitra yang lolos persetujuan, bukan
endpoint publik tanpa pendaftaran. Untuk traffic real-time tanpa langganan,
opsi yang realistis adalah GPS armada sendiri (perlu perangkat, internet, dan
server) atau akses resmi Waze for Cities/ATCS. Aplikasi tetap harus menandai
traffic sintetis jika tidak ada observasi aktual.
