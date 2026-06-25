import logging
from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text
from flask_cors import CORS
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity

from logic_engine import evaluasi_kondisi_mata
from datetime import datetime
import joblib
import numpy as np
import pandas as pd

from datetime import datetime, timedelta
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity
from flask_bcrypt import Bcrypt

app = Flask(__name__)
CORS(app)
bcrypt = Bcrypt(app)

# Menyembunyikan log default Flask yang berlebihan
log = logging.getLogger('werkzeug')
log.setLevel(logging.INFO)

# 🔥 KONEKSI NEON POSTGRESQL ONLINE:
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://neondb_owner:npg_eYiZXg7WMF6x@ep-soft-cake-ao44m5w0.c-2.ap-southeast-1.aws.neon.tech/neondb?sslmode=require'
# Pastikan baris track modifications ini tetap False agar tidak boros ram cloud
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['JWT_SECRET_KEY'] = 'nanda-myoguard-super-secret-key-2026' 
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(days=1)

jwt = JWTManager(app)
db = SQLAlchemy(app)

# --- MODEL DATABASE (Wajib Dideklarasikan Pertama) ---
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nama = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    tanggal_lahir = db.Column(db.Date, nullable=True)
    umur = db.Column(db.Integer, nullable=True)
    pekerjaan = db.Column(db.String(50), nullable=True)
    status_kacamata = db.Column(db.Boolean, default=False)
    lama_berkacamata = db.Column(db.String(20), nullable=True)
    sph = db.Column(db.Float, nullable=True)
    cyl = db.Column(db.Float, nullable=True)
    riwayat = db.relationship('RiwayatEvaluasi', backref='user', lazy=True)
    
class RiwayatEvaluasi(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    waktu = db.Column(db.DateTime, default=datetime.now)
    jarak_cm = db.Column(db.Float, nullable=False)
    kedipan_per_menit = db.Column(db.Integer, nullable=False)
    status_mata = db.Column(db.String(50), nullable=False)
    skor_bahaya = db.Column(db.Float, nullable=False)

# 🔥 PEMBUATAN TABEL OTOMATIS (Wajib ditaruh SETELAH model dideklarasikan)
with app.app_context():
    db.create_all()
    print("🚀 [NEON CLOUD] Struktur Database MyoGuard Terbaru Siap & Digenerate Otomatis!")

# --- MEMUAT MODEL AI (RANDOM FOREST) ---
try:
    rf_model = joblib.load('myoguard_model.pkl')
    le_waktu = joblib.load('le_waktu.pkl')
    le_target = joblib.load('le_target.pkl')
    print("🧠 Otak AI (Random Forest) activated")
except Exception as e:
    print(f"⚠️ Gagal memuat model AI: {e}")

# ... (Kode route/endpoint API kamu ada di bawah sini) ...

# --- ENDPOINT API ---

# ==========================================
# 🔥 1. ENDPOINT REGISTER (Dengan Keamanan Bcrypt & Anti-Spasi)
# ==========================================
@app.route('/api/register', methods=['POST'])
def register():
    data = request.json
    email_input = data['email'].strip()
    password_input = data['password'].strip()
    
    try:
        user_eksis = User.query.filter_by(email=email_input).first()
        
        # Enkripsi password mentah menjadi Hash Bcrypt
        password_hash = bcrypt.generate_password_hash(password_input).decode('utf-8')
        
        if user_eksis:
            # Jika user sebelumnya mendaftar via Google lalu membuat password
            user_eksis.password = password_hash
            db.session.commit()
            return jsonify({"message": "Password akun berhasil dikonfigurasi!", "user_id": user_eksis.id}), 201
            
        new_user = User(
            nama=data['nama'].strip(), 
            email=email_input,
            password=password_hash # Simpan versi aman ke database
        )
        db.session.add(new_user)
        db.session.commit()
        return jsonify({"message": "User berhasil terdaftar", "user_id": new_user.id}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Detail Error: {str(e)}"}), 400
    
# ==========================================
# 2. Update Profil Dasar
# ==========================================
@app.route('/api/update-profil-dasar', methods=['PUT'])
@jwt_required()
def update_profil_dasar():
    try:
        # Konversi identitas JWT ke integer secara tegas
        user_id = int(get_jwt_identity())
        user = User.query.get(user_id)
        
        if not user:
            return jsonify({"error": "User tidak ditemukan"}), 404
            
        data = request.json
        user.nama = data.get('nama', user.nama).strip()
        
        tgl_teks = data.get('tanggal_lahir')
        if tgl_teks and tgl_teks != "":
            try:
                user.tanggal_lahir = datetime.strptime(tgl_teks, "%Y-%m-%d").date()
            except ValueError:
                pass 
                
        user.umur = data.get('umur', user.umur)
        user.pekerjaan = data.get('pekerjaan', user.pekerjaan)
        
        db.session.commit()
        
        return jsonify({
            "status": "success",
            "user": {
                "nama": user.nama,
                "tanggal_lahir": str(user.tanggal_lahir) if user.tanggal_lahir else "",
                "umur": user.umur,
                "pekerjaan": user.pekerjaan
            }
        }), 200
    except Exception as e:
        db.session.rollback() # Kunci pengaman transaksi cloud Neon
        return jsonify({"status": "error", "message": str(e)}), 500

# ==========================================
# 3. Update Riwayat Medis
# ==========================================
@app.route('/api/update-riwayat-medis', methods=['PUT'])
@jwt_required()
def update_riwayat_medis():
    try:
        user_id = int(get_jwt_identity())
        user = User.query.get(user_id)
        
        if not user:
            return jsonify({"error": "User tidak ditemukan"}), 404
            
        data = request.json
        user.sph = data.get('sph', user.sph)
        user.cyl = data.get('cyl', user.cyl)
        user.status_kacamata = data.get('status_kacamata', user.status_kacamata)
        user.lama_berkacamata = data.get('lama_berkacamata', user.lama_berkacamata)
        
        db.session.commit()
        
        return jsonify({
            "status": "success",
            "user": {
                "sph": user.sph,
                "cyl": user.cyl,
                "status_kacamata": user.status_kacamata,
                "lama_berkacamata": user.lama_berkacamata
            }
        }), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500

# ==========================================
# 🔥 4. Ganti Password (Verifikasi Hash Lama vs Baru)
# ==========================================
@app.route('/api/ganti-password', methods=['PUT'])
@jwt_required()
def ganti_password():
    user = User.query.get(get_jwt_identity())
    if not user:
        return jsonify({"error": "User tidak ditemukan"}), 404
        
    data = request.json
    password_lama = data.get('password_lama', '').strip()
    password_baru = data.get('password_baru', '').strip()
    
    # Cek apakah password lama yang dimasukkan sesuai dengan hash di database
    if not bcrypt.check_password_hash(user.password, password_lama):
        return jsonify({"status": "error", "message": "Password lama salah!"}), 400
        
    # Enkripsi password baru sebelum menyimpannya
    user.password = bcrypt.generate_password_hash(password_baru).decode('utf-8')
    db.session.commit()
    return jsonify({"status": "success"}), 200
    
# ==========================================
# 🔥 5. Login Manual (Pengecekan Hash Bcrypt)
# ==========================================
@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    email_input = data.get('email', '').strip()
    password_input = data.get('password', '').strip()
    
    user = User.query.filter_by(email=email_input).first()
    
    # Pengecekan keamanan: Cocokkan password teks dengan hash di database
    if user and bcrypt.check_password_hash(user.password, password_input):
        access_token = create_access_token(identity=str(user.id)) 
        return jsonify({
            "status": "success",
            "message": "Login berhasil",
            "user_id": user.id,
            "nama": user.nama,
            "email": user.email,
            "login_method": "email",
            "token": access_token,
            "tanggal_lahir": str(user.tanggal_lahir) if user.tanggal_lahir else "",
            "umur": user.umur if user.umur else 0,
            "pekerjaan": user.pekerjaan if user.pekerjaan else "",
            "status_kacamata": user.status_kacamata,
            "lama_berkacamata": user.lama_berkacamata if user.lama_berkacamata else "",
            "sph": user.sph if user.sph else 0.0,
            "cyl": user.cyl if user.cyl else 0.0,
        }), 200
    else:
        return jsonify({"status": "error", "message": "Email atau password salah!"}), 401

# ==========================================
# 6. Google Login
# ==========================================
@app.route('/api/google-login', methods=['POST'])
def google_login():
    try:
        data = request.json
        email = data.get('email')
        nama = data.get('nama')
        
        if not email:
            return jsonify({"status": "error", "message": "Data email tidak valid"}), 400

        user = User.query.filter_by(email=email).first()

        if user:
            access_token = create_access_token(identity=str(user.id))
            return jsonify({
                "status": "success",
                "message": "Login berhasil via Google",
                "user_id": user.id,
                "nama": user.nama,
                "email": user.email,
                "login_method": "google",
                "token": access_token,
                "tanggal_lahir": str(user.tanggal_lahir) if user.tanggal_lahir else "",
                "umur": user.umur if user.umur else 0,
                "pekerjaan": user.pekerjaan if user.pekerjaan else "",
                "status_kacamata": user.status_kacamata,
                "lama_berkacamata": user.lama_berkacamata if user.lama_berkacamata else "",
                "sph": user.sph if user.sph else 0.0,
                "cyl": user.cyl if user.cyl else 0.0,
            }), 200
        else:
            return jsonify({
                "status": "needs_password",
                "email": email,
                "nama": nama,
                "message": "Akun belum terdaftar. Silakan buat password."
            }), 200

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
@app.route('/api/guard-mode/evaluate', methods=['POST'])
def evaluate_realtime():
    data = request.json
    raw_user_id = data.get('user_id') 
    if not raw_user_id:
        return jsonify({"error": "user_id wajib dikirim!"}), 400

    # 🔥 Konversi paksa ke integer agar PostgreSQL Neon aman
    user_id = int(raw_user_id)
    jarak = data.get('jarak_cm', 35)
    kedipan = data.get('kedipan_per_menit', 15)
    
    hasil_analisis = evaluasi_kondisi_mata(jarak_cm=jarak, kedipan_per_menit=kedipan)
    
    try:
        catatan_baru = RiwayatEvaluasi(
            user_id=user_id,
            jarak_cm=float(jarak),
            kedipan_per_menit=int(kedipan),
            status_mata=hasil_analisis['status_mata'],
            skor_bahaya=float(hasil_analisis['skor_bahaya'])
        )
        db.session.add(catatan_baru)
        db.session.commit()
        return jsonify({"status": "success", "hasil_keputusan": hasil_analisis}), 200
    except Exception as e:
        db.session.rollback() # 🔥 Tambahan penting jika insert gagal
        return jsonify({"error": str(e)}), 500
    
# Tambahkan rute ini di bawah rute-rute yang sudah ada
@app.route('/api/analitik/<int:user_id>', methods=['GET'])
def get_analitik(user_id):
    try:
        # 🔥 Perbaikan Raw SQL dari MySQL ke sintaks PostgreSQL
        results = db.session.execute(
            text("""
                SELECT 
                    DATE(waktu) as tanggal,
                    AVG(jarak_cm) as rata_jarak,
                    AVG(kedipan_per_menit) as rata_kedipan,
                    COUNT(id) as frekuensi_sesi 
                FROM riwayat_evaluasi
                WHERE user_id = :uid 
                AND waktu >= CURRENT_DATE - INTERVAL '7 days'
                GROUP BY DATE(waktu)
                ORDER BY tanggal ASC
            """), 
            {"uid": user_id}
        ).fetchall()

        data_harian = []
        for row in results:
            data_harian.append({
                "tanggal": str(row.tanggal),
                "rata_jarak": round(float(row.rata_jarak or 0), 1),
                "rata_kedipan": round(float(row.rata_kedipan or 0), 1),
                "estimasi_jam_screen_time": round(float(row.frekuensi_sesi or 0) * 0.1, 1)
            })

        return jsonify({
            "status": "success", 
            "user_target": user_id, 
            "data": data_harian
        }), 200

    except Exception as e:
        print(f"Error Analitik Postgres: {e}") 
        return jsonify({"status": "error", "pesan": str(e)}), 500
     

@app.route('/api/history/<int:user_id>', methods=['GET'])
def get_history(user_id):
    try:
        riwayat_user = RiwayatEvaluasi.query.filter_by(user_id=user_id).order_by(RiwayatEvaluasi.waktu.desc()).limit(20).all()
        if not riwayat_user:
            return jsonify({"message": "Belum ada riwayat untuk user ini", "data": []}), 200

        data_format = []
        for r in riwayat_user:
            data_format.append({
                "id_riwayat": r.id,
                "waktu": r.waktu.strftime("%Y-%m-%d %H:%M:%S"),
                "jarak_cm": r.jarak_cm,
                "kedipan_per_menit": r.kedipan_per_menit,
                "status_mata": r.status_mata,
                "skor_bahaya": r.skor_bahaya
            })
        return jsonify({"status": "success", "user_id": user_id, "total_data": len(data_format), "data": data_format}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
@app.route('/api/predict-risk', methods=['POST'])
def predict_risk():
    try:
        data = request.get_json(silent=True) or {}
        durasi = data.get('durasi_layar_menit', 60)
        waktu_teks = data.get('waktu_penggunaan', 'Siang')
        jarak = float(data.get('rata_rata_jarak_cm', 35.0))
        kedipan = int(data.get('rata_rata_kedipan_bpm', 15))
        pelanggaran = data.get('total_pelanggaran_jarak', 0)

        # 1. Logic Machine Learning (Base Prediction)
        if waktu_teks not in le_waktu.classes_:
            waktu_teks = 'Siang'
        waktu_encoded = le_waktu.transform([waktu_teks])[0]

        fitur_input = pd.DataFrame([[durasi, waktu_encoded, jarak, kedipan, pelanggaran]], 
            columns=['durasi_layar_menit', 'waktu_penggunaan', 'rata_rata_jarak_cm', 
                     'rata_rata_kedipan_bpm', 'total_pelanggaran_jarak'])

        prediksi_encoded = rf_model.predict(fitur_input)[0]
        hasil_prediksi = le_target.inverse_transform([prediksi_encoded])[0]

        # 2. 🔥 SAFETY OVERRIDE (Logika Paksaan untuk Demo)
        # Jika jarak < 25cm ATAU kedipan < 8 kali/menit, APA PUN kata ML, tetap jadi Tinggi!
        if jarak < 25.0 or kedipan < 8:
            hasil_prediksi = "Tinggi"
        elif jarak < 30.0 and hasil_prediksi == "Aman":
            hasil_prediksi = "Sedang"

        # 3. Pesan Medis Dinamis
        if hasil_prediksi == "Tinggi":
            pesan_medis = "Risiko sangat tinggi! Segera istirahatkan matamu pakai aturan 20-20-20."
        elif hasil_prediksi == "Sedang":
            pesan_medis = "Mata mulai lelah. Jangan lupa berkedip dan perbaiki jarak dudukmu."
        else:
            pesan_medis = "Aman! Kebiasaan menatap layarmu sudah cukup baik."

        return jsonify({
            "status": "success",
            "fitur_masuk": {
                "durasi_menit": durasi,
                "waktu": waktu_teks,
                "jarak_cm": jarak,
                "kedipan_bpm": kedipan,
                "pelanggaran": pelanggaran
            },
            "prediksi_risiko": hasil_prediksi,
            "rekomendasi": pesan_medis
        }), 200
    except Exception as e:
        print(f"Error Prediksi: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    print("Server MyoGuard berjalan di port 5000...")
    app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=False)