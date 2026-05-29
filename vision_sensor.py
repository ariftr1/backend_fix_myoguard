import cv2
import time
import requests
import math
import mediapipe as mp
from datetime import datetime

# --- 1. KONFIGURASI MEDIAPIPE ---
mp_face_mesh = mp.solutions.face_mesh
face_mesh = mp_face_mesh.FaceMesh(
    max_num_faces=1,
    refine_landmarks=True,
    min_detection_confidence=0.5,
    min_tracking_confidence=0.5
)

# --- 2. KONSTANTA & KALIBRASI MOBILE ---
REAL_FACE_WIDTH_CM = 14.0 
FOCAL_LENGTH = 430.0  # Default, nanti bisa diubah lewat kalibrasi
JARAK_AMAN_MIN = 40.0 # Batas minimal jarak aman (cm)

EAR_THRESHOLD = 0.21  
blink_count = 0
mata_tertutup = False
waktu_tutup_mata = 0.0 # 🔥 Variabel baru untuk mengukur durasi mata tertutup

session_start_time = time.time()
last_blink_time = time.time()

# 🔥 Variabel baru untuk Smart Alerts (Peringatan Santun)
waktu_mulai_pelanggaran = None 
state_bahaya = False

# --- 3. URL API MYOGUARD ---
API_URL = "http://127.0.0.1:5000/api/guard-mode/evaluate"
API_AI_URL = "http://127.0.0.1:5000/api/predict-risk"

# --- 4. PERSIAPAN REKAP SESI AI ---
jam_sekarang = datetime.now().hour
if 5 <= jam_sekarang < 15:
    waktu_teks = "Pagi"
elif 15 <= jam_sekarang < 18:
    waktu_teks = "Siang"
else:
    waktu_teks = "Malam"

history_jarak = []
history_bpm = []
total_pelanggaran = 0

# --- 5. FUNGSI MATEMATIKA ---
def hitung_jarak(titik_kiri, titik_kanan, lebar_frame):
    lebar_wajah_pixel = abs(titik_kanan.x - titik_kiri.x) * lebar_frame
    if lebar_wajah_pixel == 0: return 0, 0
    jarak = (REAL_FACE_WIDTH_CM * FOCAL_LENGTH) / lebar_wajah_pixel
    return jarak, lebar_wajah_pixel # Return pixel juga untuk keperluan kalibrasi

def hitung_ear(mata, landmarks, w, h):
    p2_p6 = math.dist([landmarks[mata[1]].x*w, landmarks[mata[1]].y*h], 
                      [landmarks[mata[5]].x*w, landmarks[mata[5]].y*h])
    p3_p5 = math.dist([landmarks[mata[2]].x*w, landmarks[mata[2]].y*h], 
                      [landmarks[mata[4]].x*w, landmarks[mata[4]].y*h])
    p1_p4 = math.dist([landmarks[mata[0]].x*w, landmarks[mata[0]].y*h], 
                      [landmarks[mata[3]].x*w, landmarks[mata[3]].y*h])
    if p1_p4 == 0: return 0
    return (p2_p6 + p3_p5) / (2.0 * p1_p4)

# --- 6. INISIALISASI KAMERA ---
cap = cv2.VideoCapture(1) # Ubah ke 0 jika kamera eksternal tidak terbaca
print("Kamera MyoGuard Aktif (Mode Kalibrasi Mobile)...")
print("INFO: Tekan tombol 'c' di keyboard untuk KALIBRASI jarak aman ke 50cm.")

mata_kiri_idx = [33, 160, 158, 133, 153, 144]
mata_kanan_idx = [362, 385, 387, 263, 373, 380]
waktu_kirim_terakhir = time.time()

# --- 7. LOOPING UTAMA SENSOR ---
while cap.isOpened():
    success, image = cap.read()
    if not success: break
    
    h, w, _ = image.shape
    image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    results = face_mesh.process(image_rgb)

    jarak_cm = 0 
    lebar_wajah_px = 0
    
    if results.multi_face_landmarks:
        for face_landmarks in results.multi_face_landmarks:
            # Hitung Jarak
            pipi_kiri = face_landmarks.landmark[234]
            pipi_kanan = face_landmarks.landmark[454]
            jarak_cm, lebar_wajah_px = hitung_jarak(pipi_kiri, pipi_kanan, w)
            
            # 🔥 LOGIKA FILTER KEDIPAN (Anti-Spam Melirik Bawah)
            ear_kiri = hitung_ear(mata_kiri_idx, face_landmarks.landmark, w, h)
            ear_kanan = hitung_ear(mata_kanan_idx, face_landmarks.landmark, w, h)
            rata_rata_ear = (ear_kiri + ear_kanan) / 2.0
            
            if rata_rata_ear < EAR_THRESHOLD:
                if not mata_tertutup:
                    waktu_tutup_mata = time.time() # Mulai hitung stopwatch saat mata tertutup
                    mata_tertutup = True 
            else:
                if mata_tertutup:
                    durasi_tutup = time.time() - waktu_tutup_mata
                    mata_tertutup = False
                    
                    # Cek durasi: Kedipan manusia normal sangat cepat (0.05 s.d 0.4 detik)
                    # Jika tertutup lebih dari 0.4 detik, itu melirik bawah atau ketiduran! (Abaikan)
                    if 0.05 < durasi_tutup < 0.4:
                        blink_count += 1
            
            # 🔥 LOGIKA SMART ALERTS (Peringatan Santun)
            if jarak_cm > 0 and jarak_cm < JARAK_AMAN_MIN:
                # Jika jarak melanggar batas, mulai hitung waktu
                if waktu_mulai_pelanggaran is None:
                    waktu_mulai_pelanggaran = time.time()
                # Jika melanggar berturut-turut selama lebih dari 3 DETIK
                elif time.time() - waktu_mulai_pelanggaran >= 3.0:
                    state_bahaya = True
            else:
                # Jika pengguna kembali ke jarak aman, reset semuanya
                waktu_mulai_pelanggaran = None
                state_bahaya = False

            # Tampilkan Indikator di Layar Kamera
            warna_teks = (0, 0, 255) if state_bahaya else ((0, 255, 255) if jarak_cm < JARAK_AMAN_MIN else (0, 255, 0))
            
            # Simulasi Pop-Up Notifikasi di Terminal
            if state_bahaya:
                cv2.putText(image, "AWAS! TERLALU DEKAT!", (20, 130), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 3)

            cv2.putText(image, f"Jarak: {int(jarak_cm)} cm", (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, warna_teks, 2)
            cv2.putText(image, f"Total Kedip: {blink_count}", (20, 90), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 100, 0), 2)

    # --- 8. KIRIM DATA KE DATABASE & REKAM UNTUK AI (Tiap 5 Detik) ---
    waktu_sekarang = time.time()
    if waktu_sekarang - waktu_kirim_terakhir >= 5.0:
        durasi_berjalan_menit = (waktu_sekarang - session_start_time) / 60.0
        bpm_sekarang = int(blink_count / durasi_berjalan_menit) if durasi_berjalan_menit > 0 else 0
        
        # Masukkan ke Memori AI
        history_jarak.append(jarak_cm)
        history_bpm.append(bpm_sekarang)
        if state_bahaya: # Sekarang pelanggaran dihitung jika state_bahaya aktif (sudah > 3 detik)
            total_pelanggaran += 1
        
        # Tembak API MySQL
        data_payload = {
            "user_id": 1,
            "jarak_cm": round(jarak_cm, 2),
            "kedipan_per_menit": bpm_sekarang
        }
        
        try:
            response = requests.post(API_URL, json=data_payload)
            if response.status_code == 200:
                print(f"Data DB -> Jarak: {int(jarak_cm)}cm, BPM: {bpm_sekarang} | State Bahaya: {state_bahaya}")
        except Exception as e:
            pass 
            
        waktu_kirim_terakhir = waktu_sekarang

    cv2.imshow('Sensor MyoGuard (Simulasi Mobile)', image)
    
    key = cv2.waitKey(5) & 0xFF
    # 🔥 FITUR KALIBRASI (Tekan 'c')
    if key == ord('c') and lebar_wajah_px > 0:
        # Asumsikan saat tombol 'c' ditekan, pengguna sedang duduk tegak di jarak ideal 50cm
        FOCAL_LENGTH = (lebar_wajah_px * 50.0) / REAL_FACE_WIDTH_CM
        print(f"\n[KALIBRASI SUKSES] Focal Length baru: {FOCAL_LENGTH:.2f}. Jarak acuan disetel ke 50cm.")
    
    # Tekan 'q' atau Esc untuk berhenti
    elif key in [27, ord('q')]:
        break

cap.release()
cv2.destroyAllWindows()

# =====================================================================
# --- 9. SETELAH KAMERA MATI: LAPORKAN KE OTAK AI MYOGUARD ---
# =====================================================================
print("\n[SESI SELESAI] Menghitung rekam medis sesi ini...")

waktu_selesai_sesi = time.time()
durasi_detik = waktu_selesai_sesi - session_start_time
durasi_menit = durasi_detik / 60.0

if durasi_menit < 1.0:
    durasi_menit += 120.0 

if len(history_jarak) > 0:
    rata_jarak = sum(history_jarak) / len(history_jarak)
    rata_bpm = sum(history_bpm) / len(history_bpm)
    
    payload_ai = {
        "durasi_layar_menit": durasi_menit, 
        "waktu_penggunaan": waktu_teks,
        "rata_rata_jarak_cm": rata_jarak,
        "rata_rata_kedipan_bpm": rata_bpm,
        "total_pelanggaran_jarak": total_pelanggaran
    }
    
    print("\nMengirim Laporan ke Otak AI MyoGuard...")
    
    try:
        res_ai = requests.post(API_AI_URL, json=payload_ai)
        if res_ai.status_code == 200:
            hasil_ai = res_ai.json()
            print("\n" + "="*45)
            print(" 🤖 HASIL DIAGNOSIS AI MYOGUARD (END SESSION) 🤖")
            print("="*45)
            print(f"Durasi Sesi  : {durasi_menit:.2f} menit (Simulasi)")
            print(f"Rata Jarak   : {rata_jarak:.2f} cm")
            print(f"Rata Kedipan : {rata_bpm:.0f}x / menit")
            print(f"Pelanggaran  : {total_pelanggaran} kali")
            print(f"Waktu        : {waktu_teks}")
            print("-"  * 45)
            print(f"🚨 RISIKO MATA    : {hasil_ai['prediksi_risiko'].upper()} 🚨")
            print(f"💡 Rekomendasi    : {hasil_ai['rekomendasi']}")
            print("="*45 + "\n")
        else:
            print("Gagal mendapat respons AI:", res_ai.text)
    except Exception as e:
        print("Server AI belum menyala atau koneksi terputus:", e)