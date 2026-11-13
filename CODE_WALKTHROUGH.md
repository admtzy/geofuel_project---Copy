# Panduan membaca kode GEO-FUEL

## 1. Satu alur request

1. Browser pada `geofuel/static/index.html` mengirim parameter ke FastAPI (`POST /api/run` atau `POST /api/compare`).
2. `api.py` memanggil `load_graph()` dan `make_instance()`.
3. `data.py` membaca CSV SPBU dan armada, mengambil jaringan OSMnx atau grid offline, snap koordinat ke node jalan, lalu membentuk matriks jarak, waktu, dan jalur.
4. `inventory.py` menghitung DOI, safety stock, waktu sampai safety stock, lead time, volume pengiriman, titik pemesanan ulang, dan prioritas.
5. `simulation.py` memilih kandidat dan menjalankan M0/M1 atau memanggil `model.py` untuk M2/M3.
6. `model.py` membuat variabel keputusan MILP, fungsi tujuan, kendala kendaraan, stok terminal, jendela penerimaan, dan subtour; HiGHS menyelesaikannya.
7. `simulation.py` menjalankan perjalanan, loading, unloading, konsumsi stok, penerimaan BBM, dan rolling horizon.
8. `api.py` mengubah hasil menjadi JSON dan Leaflet menampilkannya.

## 2. Rumus keputusan SPBU

Untuk setiap SPBU:

- DOI = stok sekarang / konsumsi harian.
- Safety stock = `z * sqrt(L * sigma_demand^2 + demand^2 * sigma_lead_time^2)`.
- Time-to-safety = `(stok - safety_stock) / demand * 24` jam.
- Effective lead time = loading + perjalanan + unloading.
- Trigger pengiriman = stok <= safety stock atau time-to-safety <= effective lead time + buffer.
- Kebutuhan kirim = proyeksi stok saat tiba menuju target fill ratio, dengan batas kapasitas tangki.

Sumber simpangan baku demand dapat berasal dari riwayat penjualan harian. Jika kosong, kode memakai default asumsi 20% dari rata-rata demand.

## 3. Arti variabel MILP

- `x[i,j,k]`: kendaraan k bergerak dari simpul i ke j.
- `y[i,k]`: SPBU i dilayani kendaraan k.
- `z[k]`: kendaraan k digunakan.
- `q[i,k]`: liter yang dikirim kendaraan k ke SPBU i.
- `u[i]`: kebutuhan SPBU i yang tidak terpenuhi.
- `T[i,k]`: waktu mulai pelayanan di SPBU i oleh kendaraan k.
- `L[i]`: keterlambatan.
- `r[i,k]`: urutan kunjungan untuk mencegah subtour.

Kendala terminal membatasi total `q` terhadap stok terminal yang tersedia. Kendala per kendaraan membatasi total volume muatan terhadap kapasitas truk.

## 4. Perbedaan M0–M3

- M0 memilih kandidat dari jarak terdekat.
- M1 mengutamakan time-to-safety paling kecil lalu menyusun urutan kunjungan.
- M2 menyelesaikan HFVRPTW dengan waktu dasar free-flow.
- M3 menyelesaikan HFVRPTW dengan estimasi waktu yang sudah dikalikan faktor skenario lalu lintas.

Jika Pyomo/HiGHS tidak tersedia atau solver gagal menghasilkan solusi yang dapat dibaca, M2/M3 boleh memakai fallback M1 untuk menjaga demo tetap berjalan. Setiap siklus fallback diberi flag. Siklus tersebut bukan hasil optimasi MILP.

## 5. Simulasi dan rolling horizon

Simulasi berlangsung dari jam 06.00 sampai 22.00. Demand dikurangi bertahap setiap 15 menit. BBM yang dikirim baru masuk stok SPBU setelah proses bongkar selesai. Stok terminal dikurangi ketika kendaraan berangkat membawa muatan. Kendaraan baru tersedia lagi setelah kembali ke terminal.

Setiap `epoch_hours` sistem membaca stok terbaru, mengecek kendaraan yang idle, memperbarui kandidat, dan menyusun rencana berikutnya. Kendaraan yang sedang menjalankan rute tidak dipindahkan secara tiba-tiba.

## 6. Indikator evaluasi

- `total_cost_rp`: biaya jarak, waktu mengemudi/pelayanan, biaya tetap trip, penalti keterlambatan, dan penalti stockout.
- `distance_km`: total jarak rute.
- `driving_hours`: total jam perjalanan.
- `service_hours`: loading + unloading.
- `delivered_liters`: total volume dikirim.
- `stockout_liters`: konsumsi yang tidak dapat dipenuhi karena stok habis.
- `service_level`: proporsi demand horizon yang terpenuhi.
- `on_time_rate`: proporsi stop yang mulai dilayani tidak melewati batas waktu penerimaan.
- `fleet_utilization`: volume kirim dibagi kapasitas kendaraan pada trip yang dijalankan.

Biaya dan hasil hanya merupakan hasil simulasi selama input masih sintetis. Untuk menilai manfaat aktual, diperlukan data historis operasional dan baseline pembanding yang tervalidasi.

## 8. Catatan konsistensi waktu dan batas interpretasi

- Waktu loading dicatat satu kali pada awal trip. Waktu loading terpisah dari waktu bongkar agar komponen biaya simulasi tidak menggandakan biaya loading.
- Waktu pelayanan SPBU mencakup waktu dasar bongkar dan volume dibagi laju bongkar. Waktu menunggu karena kendaraan datang sebelum jendela dibuka belum dimasukkan sebagai komponen biaya tenaga kerja terpisah.
- Matriks OD menggunakan jalur terpendek berdasarkan panjang. Waktu pada jalur itu dijumlahkan dari atribut `travel_time`. M3 mengalikan waktu OD dengan faktor skenario; ia belum mencari jalur alternatif per segmen jalan berdasarkan traffic real-time.
- Safety stock dapat memakai simpangan baku penjualan harian historis dari `prepare_actual_stations.py`. Bila kolom historis tidak tersedia, demand standard deviation diisi dengan asumsi 20% dari rata-rata demand.
- Stok terminal membatasi total pengiriman, tetapi pasokan masuk ke terminal selama horizon belum dimodelkan.
