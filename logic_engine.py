# logic_engine.py

def evaluasi_kondisi_mata(jarak_cm, kedipan_per_menit):
    """
    Update Parameter Berdasarkan Jurnal:
    - Jarak Normal: 33 - 40 cm
    - Kedipan Normal: 15 - 20 kali/menit
    """
    
    # 1. Menentukan Skor Jarak
    if jarak_cm < 25:
        skor_jarak = 100  # Kritis (Sangat jauh di bawah standar 33cm)
    elif 25 <= jarak_cm < 33:
        skor_jarak = 50   # Waspada (Mulai mendekati batas bawah 33cm)
    else:
        skor_jarak = 0    # Aman (Sudah di zona 33-40cm atau lebih)

    # 2. Menentukan Skor Kedipan
    if kedipan_per_menit < 10:
        skor_kedipan = 100 # Kritis (Sangat kurang dari standar 15 bpm)
    elif 10 <= kedipan_per_menit < 15:
        skor_kedipan = 50  # Waspada (Mulai lupa berkedip)
    else:
        skor_kedipan = 0   # Aman (Sudah di zona 15-20 bpm atau lebih)

    # 3. Penggabungan Skor (Fuzzy Logic Sederhana)
    skor_total = (skor_jarak + skor_kedipan) / 2

    # Penentuan Status & Rekomendasi Berdasarkan Standar Jurnal
    if skor_total >= 75:
        status = "Kritis"
        pesan = "Peringatan! Jarak terlalu dekat (<33cm) & mata sangat jarang berkedip. Risiko Miopia meningkat!"
    elif skor_total >= 50:
        status = "Waspada"
        pesan = "Posisi mulai tidak ideal. Pastikan jarak layar minimal 33cm dan usahakan lebih sering berkedip."
    else:
        status = "Aman"
        pesan = "Kondisi mata terjaga. Jarak dan frekuensi kedipan sesuai standar kesehatan."

    return {
        "status_mata": status,
        "pesan_rekomendasi": pesan,
        "skor_bahaya": skor_total,
        "metadata": {
            "standar_jarak": "33-40 cm",
            "standar_kedipan": "15-20 bpm"
        }
    }

if __name__ == "__main__":
    # Test dengan angka yang baru saja kamu temukan
    # Simulasi: Jarak 30cm (Waspada) dan Kedipan 12 (Waspada)
    hasil = evaluasi_kondisi_mata(jarak_cm=30, kedipan_per_menit=12)
    print("--- EVALUASI BERDASARKAN STANDAR JURNAL ---")
    print(f"Status: {hasil['status_mata']}")
    print(f"Pesan : {hasil['pesan_rekomendasi']}")