# Register sumber data GEO-FUEL

| Data | Sumber | Bentuk | Peran dalam model | Batasan |
|---|---|---|---|---|
| Identitas/kode/alamat/status SPBU Kota Bandung | ESDM, Penyalur BBM Retail PT Pertamina Patra Niaga Semester I 2025 | CSV hasil ekstraksi dokumen resmi | Master identitas fasilitas | Tidak berisi koordinat, penjualan, stok, kapasitas tangki, atau relasi terminal-ke-SPBU |
| Koordinat fasilitas dan jaringan jalan | OpenStreetMap melalui Nominatim/OSMnx | API/peta | Geocoding kandidat dan routing | Koordinat hasil geocoding wajib diperiksa; OSM bisa tidak lengkap atau tidak mutakhir |
| Populasi per kecamatan | Open Data Kota Bandung / Disdukcapil | Dataset publik | Variabel konteks/proxy potensi permintaan, bukan konsumsi BBM | Tidak digunakan sebagai penjualan BBM; tidak otomatis menjadi demand SPBU |
| Prakiraan cuaca | BMKG Data Prakiraan Cuaca Terbuka | JSON API | Variabel konteks cuaca (opsional) | Hanya prakiraan 3 hari, bukan histori cuaca atau kemacetan |
| Stok, kapasitas tangki, demand, lead time | Tidak ditemukan sebagai dataset publik SPBU yang dapat diverifikasi | Parameter skenario dalam file runnable | Input wajib model inventory | Harus diganti data internal/observasi bila ingin klaim empiris |
| Kapasitas dan jumlah armada | Tidak ditemukan sebagai data publik terverifikasi Fuel Terminal Ujung Berung | Parameter skenario dalam file runnable | Input wajib HFVRPTW | Bukan armada aktual Pertamina |
| Traffic real-time | Tidak tersedia dalam integrasi kode ini | Tidak digunakan sebagai real-time | Belum menjadi input aktual | M3 tetap skenario faktor waktu tempuh, bukan traffic sensor langsung |

## URL sumber

- ESDM SPBU retail Semester I 2025: https://migas.esdm.go.id/cms/uploads/informasi-publik/BU_hilir/2025%20-%20BBM%20Semester%20I/Penyalur%20Agen%20Retail%20PT%20PPN%20SMT%20I%202025.pdf
- Open Data Bandung jumlah penduduk kecamatan: https://opendata.bandung.go.id/dataset/jumlah-penduduk-kota-bandung-berdasarkan-kecamatan
- OpenStreetMap copyright/ODbL: https://www.openstreetmap.org/copyright
- Nominatim usage policy: https://operations.osmfoundation.org/policies/nominatim/
- BMKG open forecast API: https://data.bmkg.go.id/prakiraan-cuaca/
- BMKG API endpoint: https://api.bmkg.go.id/publik/prakiraan-cuaca?adm4={kode_wilayah_administrasi_desa}
- Pertamina OneSolution terminal network (alamat terminal): https://onesolution.pertamina.com/Network/Market?office_type=TBBM&type=IFM

## Status ilmiah

File `stations_public_runnable.csv` menggabungkan identitas publik dan koordinat kandidat dengan parameter operasional yang sengaja diberi label asumsi. Ia membuat pipeline dapat dieksekusi, tetapi hasil optimasi hanya merupakan eksperimen skenario, bukan evaluasi kinerja distribusi Pertamina aktual.
