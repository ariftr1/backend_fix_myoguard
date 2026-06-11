from google.oauth2 import id_token
from google.auth.transport import requests as google_requests

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

from flask import jsonify

app = Flask(__name__)
CORS(app)

# Konfigurasi Koneksi MySQL
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root:@localhost/myoguard_db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['JWT_SECRET_KEY'] = 'nanda-myoguard-super-secret-key-2026' 
jwt = JWTManager(app)

db = SQLAlchemy(app)

# --- MODEL DATABASE ---
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nama = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    riwayat = db.relationship('RiwayatEvaluasi', backref='user', lazy=True)
    
class RiwayatEvaluasi(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    waktu = db.Column(db.DateTime, default=datetime.now)
    jarak_cm = db.Column(db.Float, nullable=False)
    kedipan_per_menit = db.Column(db.Integer, nullable=False)
    status_mata = db.Column(db.String(50), nullable=False)
    skor_bahaya = db.Column(db.Float, nullable=False)

# Sinkronisasi Tabel
with app.app_context():
    db.create_all()
    print("Struktur Database MyoGuard Terbaru Siap!")

# --- MEMUAT MODEL AI (RANDOM FOREST) ---
try:
    rf_model = joblib.load('myoguard_model.pkl')
    le_waktu = joblib.load('le_waktu.pkl')
    le_target = joblib.load('le_target.pkl')
    print("🧠 Otak AI (Random Forest) berhasil diaktifkan!")
except Exception as e:
    print(f"⚠️ Gagal memuat model AI: {e}")

# --- ENDPOINT API ---

@app.route('/api/register', methods=['POST'])
def register():
    data = request.json
    try:
        new_user = User(
            nama=data['nama'], 
            email=data['email'],
            password=data['password'] 
        )
        db.session.add(new_user)
        db.session.commit()
        return jsonify({"message": "User berhasil terdaftar", "user_id": new_user.id}), 201
    except Exception as e:
        return jsonify({"error": f"Detail Error: {str(e)}"}), 400
    
@app.route('/api/update-profile', methods=['PUT'])
@jwt_required()
def update_profile():
    current_user_id = get_jwt_identity() 
    user = User.query.get(current_user_id)
    
    if not user:
        return jsonify({"error": "User tidak ditemukan"}), 404

    data = request.json
    nama_baru = data.get('nama')
    email_baru = data.get('email')
    password_lama = data.get('password_lama')
    password_baru = data.get('password_baru')

    if password_lama and password_baru:
        if user.password != password_lama:
            return jsonify({"error": "Password saat ini salah!"}), 400
        user.password = password_baru 

    try:
        user.nama = nama_baru if nama_baru else user.nama
        user.email = email_baru if email_baru else user.email
        db.session.commit()
        return jsonify({"status": "success", "message": "Profil berhasil diperbarui"}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "Email mungkin sudah digunakan"}), 500
    
@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    email_input = data.get('email')
    password_input = data.get('password')
    
    user = User.query.filter_by(email=email_input).first()
    
    if user and user.password == password_input:
        access_token = create_access_token(identity=str(user.id)) 
        return jsonify({
            "status": "success",
            "message": "Login berhasil",
            "user_id": user.id,
            "nama": user.nama,
            "email": user.email,
            "login_method": "email",
            "token": access_token
        }), 200
    else:
        return jsonify({"status": "error", "message": "Email atau password salah!"}), 401

# 🔥 INI DIA FUNGSI GOOGLE LOGIN YANG BARU (HANYA BOLEH ADA SATU!) 🔥
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
            # JIKA SUDAH ADA
            access_token = create_access_token(identity=str(user.id))
            return jsonify({
                "status": "success",
                "message": "Login berhasil via Google",
                "user_id": user.id,
                "nama": user.nama,
                "email": user.email,
                "login_method": "google",
                "token": access_token
            }), 200
        else:
            # JIKA BELUM ADA (User Baru)
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
    user_id = data.get('user_id') 
    if not user_id:
        return jsonify({"error": "user_id wajib dikirim!"}), 400

    jarak = data.get('jarak_cm', 35)
    kedipan = data.get('kedipan_per_menit', 15)
    
    hasil_analisis = evaluasi_kondisi_mata(jarak_cm=jarak, kedipan_per_menit=kedipan)
    
    try:
        catatan_baru = RiwayatEvaluasi(
            user_id=user_id,
            jarak_cm=jarak,
            kedipan_per_menit=kedipan,
            status_mata=hasil_analisis['status_mata'],
            skor_bahaya=hasil_analisis['skor_bahaya']
        )
        db.session.add(catatan_baru)
        db.session.commit()
        return jsonify({"status": "success", "hasil_keputusan": hasil_analisis}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
# Tambahkan rute ini di bawah rute-rute yang sudah ada
@app.route('/api/analitik/<int:user_id>', methods=['GET'])
def get_analitik(user_id):
    try:
        # Kita gunakan db.session untuk query yang lebih clean
        # Filter berdasarkan user_id yang didapat dari parameter URL
        results = db.session.execute(
            text("""
                SELECT 
                    DATE(waktu) as tanggal,
                    AVG(jarak_cm) as rata_jarak,
                    AVG(kedipan_per_menit) as rata_kedipan,
                    COUNT(id) as frekuensi_sesi 
                FROM riwayat_evaluasi
                WHERE user_id = :uid 
                AND waktu >= DATE(NOW()) - INTERVAL 7 DAY
                GROUP BY DATE(waktu)
                ORDER BY tanggal ASC
            """), 
            {"uid": user_id}
        ).fetchall()

        data_harian = []
        for row in results:
            # Memastikan kolom diakses dengan benar
            data_harian.append({
                "tanggal": str(row.tanggal),
                "rata_jarak": round(float(row.rata_jarak or 0), 1),
                "rata_kedipan": round(float(row.rata_kedipan or 0), 1),
                "estimasi_jam_screen_time": round(float(row.frekuensi_sesi or 0) * 0.1, 1)
            })

        return jsonify({
            "status": "success", 
            "user_target": user_id, # Debugging: cek ID ini di Flutter
            "data": data_harian
        }), 200

    except Exception as e:
        print(f"Error Analitik: {e}") # Munculkan di terminal Flask
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
        data = request.json
        durasi = data.get('durasi_layar_menit', 60)
        waktu_teks = data.get('waktu_penggunaan', 'Siang')
        jarak = data.get('rata_rata_jarak_cm', 35.0)
        kedipan = data.get('rata_rata_kedipan_bpm', 15)
        pelanggaran = data.get('total_pelanggaran_jarak', 0)

        if waktu_teks not in le_waktu.classes_:
            waktu_teks = 'Siang'
        waktu_encoded = le_waktu.transform([waktu_teks])[0]

        fitur_input = pd.DataFrame([[durasi, waktu_encoded, jarak, kedipan, pelanggaran]], 
            columns=['durasi_layar_menit', 'waktu_penggunaan', 'rata_rata_jarak_cm', 
                     'rata_rata_kedipan_bpm', 'total_pelanggaran_jarak'])

        prediksi_encoded = rf_model.predict(fitur_input)[0]
        hasil_prediksi = le_target.inverse_transform([prediksi_encoded])[0]

        pesan_medis = ""
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
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)