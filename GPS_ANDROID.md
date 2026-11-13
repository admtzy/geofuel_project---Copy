# GPS Android ke GEO-FUEL (opsional)

Fitur ini menerima posisi kendaraan yang benar-benar dikirim oleh perangkat Android/tracker. Server **tidak dapat mengambil GPS Android secara diam-diam**. Pasang aplikasi GPS tracker/HTTP client yang mendukung pengiriman HTTP POST berkala, izinkan akses lokasi, dan arahkan ke alamat laptop.

## Endpoint

- `POST http://ALAMAT-IP-LAPTOP:8000/api/gps/update`
- `GET  http://ALAMAT-IP-LAPTOP:8000/api/gps/positions`
- `DELETE http://ALAMAT-IP-LAPTOP:8000/api/gps/positions/ID-KENDARAAN`

Contoh body JSON (kirim tiap 5–15 detik):

```json
{
  "vehicle_id": "MT-01",
  "lat": -6.9147,
  "lon": 107.6098,
  "speed_kmh": 24.5,
  "heading": 135
}
```

Koordinat di atas hanya contoh format, bukan lokasi kendaraan aktual. Ganti dengan koordinat yang diberikan perangkat.

## Cara menghubungkan

1. Laptop dan Android berada di Wi-Fi/jaringan yang sama.
2. Jalankan `ipconfig` di Windows dan cari IPv4 adapter Wi-Fi, misalnya `192.168.1.10`.
3. Izinkan Python/Uvicorn pada Windows Firewall untuk jaringan privat.
4. Pada aplikasi Android GPS tracker/HTTP request, set URL menjadi `http://192.168.1.10:8000/api/gps/update`, metode POST, header `Content-Type: application/json`, dan body sesuai format di atas. Ganti IP dengan IP laptop sendiri.
5. Buka `http://127.0.0.1:8000/docs` di laptop lalu uji `GET /api/gps/positions`.

Endpoint ini menyimpan posisi terakhir per kendaraan di memori server. Data hilang saat server restart dan belum mengubah optimasi rute otomatis. Untuk pemetaan GPS live, aplikasi perlu membaca endpoint positions secara berkala. Gunakan HTTPS dan autentikasi sebelum server dibuka ke internet; endpoint demo ini belum memiliki autentikasi.

## Batasan mode gratis

- GPS Android: live bila perangkat mengirim koordinat dan jaringan tersedia.
- Stok SPBU/terminal dan penjualan: tetap SIMULATED sampai dihubungkan ke sumber resmi atau input operator yang tervalidasi.
- Traffic: jaringan jalan OpenStreetMap + faktor skenario, bukan traffic live per ruas.
- Karena itu, keseluruhan sistem belum boleh disebut full real-time operasional. Label GPS `DEVICE_REPORTED` juga bukan verifikasi independen.
