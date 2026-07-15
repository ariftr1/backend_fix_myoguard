import logging
from flask import render_template
import random
from functools import wraps
from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text
from flask_cors import CORS
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity
from flask_mail import Mail, Message
import pymongo
import pymongo  
import plotly.express as px  
import plotly.io as pio  
from threading import Thread

from logic_engine import evaluasi_kondisi_mata
from datetime import datetime, timedelta
import joblib
import numpy as np
import pandas as pd

from flask_bcrypt import Bcrypt
from flask_mail import Mail, Message

from functools import wraps

def log_activity(activity_name):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            try:
                # 🔥 GUNAKAN verify_jwt_in_request(optional=True) 
                # Ini tidak akan crash jika token tidak ada
                from flask_jwt_extended import verify_jwt_in_request
                
                user_id = None
                try:
                    verify_jwt_in_request(optional=True)
                    user_id = get_jwt_identity()
                except:
                    user_id = None
                
                # Jika tidak ada JWT, coba ambil email dari request body
                if not user_id:
                    data = request.get_json(silent=True)
                    if data and 'email' in data:
                        user = User.query.filter_by(email=data['email']).first()
                        user_id = user.id if user else None
                
                if user_id:
                    new_log = UserLog(user_id=int(user_id), aktivitas=activity_name)
                    db.session.add(new_log)
                    db.session.commit()
                    print(f"✅ Log tercatat: {activity_name}")
            except Exception as e:
                # Kita tidak perlu rollback jika log gagal agar tidak mengganggu login user
                print(f"⚠️ Gagal catat log (bukan masalah fatal): {e}")
            return f(*args, **kwargs)
        return decorated_function
    return decorator

app = Flask(__name__)
CORS(app)
bcrypt = Bcrypt(app)

# Menyembunyikan log default Flask yang berlebihan
log = logging.getLogger('werkzeug')
log.setLevel(logging.INFO)

# 🔥 KONEKSI NEON POSTGRESQL ONLINE:
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://neondb_owner:npg_QKMRut9E6VwS@ep-wild-moon-aoac0f62-pooler.c-2.ap-southeast-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_pre_ping': True,
    'pool_recycle': 280
}
app.config['JWT_SECRET_KEY'] = 'nanda-myoguard-super-secret-key-2026'
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(days=1)

# 🔥 KONFIGURASI EMAIL OTP (Flask-Mail)
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USE_SSL'] = False
app.config['MAIL_USERNAME'] = 'ariftri1000@gmail.com'
app.config['MAIL_PASSWORD'] = 'hlapobrojczselmb' # <-- SPASI SUDAH DIHAPUS
app.config['MAIL_DEFAULT_SENDER'] = ('MyoGuard', 'ariftri1000@gmail.com')

OTP_EXPIRE_MINUTES = 5

# Ganti baris ini di app.py kamu:
MONGO_URI = "mongodb+srv://siyanto:masyanto123@cluster0.vyjoror.mongodb.net/?appName=Cluster0"
mongo_client = pymongo.MongoClient(MONGO_URI)
mongo_db = mongo_client["db_myoguard_bigdata"]  # <-- Baris ini yang mendefinisikan 'mongo_db'
print("🍃 [MONGO ATLAS] Terhubung untuk data eksternal!")

jwt = JWTManager(app)
db = SQLAlchemy(app)
mail = Mail(app)

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

    # 🔥 KOLOM BARU UNTUK OTP
    otp_code = db.Column(db.String(6), nullable=True)
    otp_expires_at = db.Column(db.DateTime, nullable=True)
    is_verified = db.Column(db.Boolean, default=False)

class RiwayatEvaluasi(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    waktu = db.Column(db.DateTime, default=datetime.now)
    jarak_cm = db.Column(db.Float, nullable=False)
    kedipan_per_menit = db.Column(db.Integer, nullable=False)
    status_mata = db.Column(db.String(50), nullable=False)
    skor_bahaya = db.Column(db.Float, nullable=False)

class UserLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    aktivitas = db.Column(db.String(255), nullable=False) 
    waktu = db.Column(db.DateTime, default=datetime.now)

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


# ==========================================
# 🔥 HELPER: Generate & Kirim OTP
# ==========================================
def send_email_background(app, msg):
    with app.app_context():
        try:
            mail.send(msg)
            print("✅ Email diproses di latar belakang.")
        except Exception as e:
            print(f"⚠️ Email gagal dikirim: {e}")

def generate_and_send_otp(user):
    otp = str(random.randint(100000, 999999))
    user.otp_code = otp
    user.otp_expires_at = datetime.now() + timedelta(minutes=OTP_EXPIRE_MINUTES)
    db.session.commit()

    msg = Message(
        subject="Kode OTP MyoGuard",
        recipients=[user.email],
        body=(
            f"Halo {user.nama},\n\n"
            f"Kode OTP kamu adalah: {otp}\n"
            f"Kode ini berlaku selama {OTP_EXPIRE_MINUTES} menit. "
            f"Jangan bagikan kode ini ke siapa pun.\n\n"
            f"- Tim MyoGuard"
        )
    )
    # Ganti baris mail.send(msg) menjadi seperti ini:
    def generate_and_send_otp(user):
        otp = str(random.randint(100000, 999999))
        user.otp_code = otp
        user.otp_expires_at = datetime.now() + timedelta(minutes=OTP_EXPIRE_MINUTES)
        db.session.commit()

        msg = Message(
            subject="Kode OTP MyoGuard",
            recipients=[user.email],
            body=(
                f"Halo {user.nama},\n\n"
                f"Kode OTP kamu adalah: {otp}\n"
                f"Kode ini berlaku selama {OTP_EXPIRE_MINUTES} menit. "
                f"Jangan bagikan kode ini ke siapa pun.\n\n"
                f"- Tim MyoGuard"
            )
    )
    
    # Menjalankan pengiriman email di proses terpisah agar tidak macet
    Thread(target=send_email_background, args=(app, msg)).start()

# ==========================================
# 🔥 1. ENDPOINT REGISTER
# ==========================================
@app.route('/api/register', methods=['POST'])
@log_activity("User melakukan pendaftaran akun baru")
def register():
    data = request.json
    email_input = data['email'].strip()
    password_input = data['password'].strip()

    try:
        user_eksis = User.query.filter_by(email=email_input).first()
        password_hash = bcrypt.generate_password_hash(password_input).decode('utf-8')

        if user_eksis:
            # Jika user sudah ada, update password dan kirim OTP kembali
            user_eksis.password = password_hash
            db.session.commit()
            # Panggil fungsi OTP via Background Thread agar tidak macet
            generate_and_send_otp(user_eksis) 
            return jsonify({"message": "Password diperbarui, silakan cek email untuk OTP!", "user_id": user_eksis.id}), 201

        # Jika user baru
        new_user = User(
            nama=data['nama'].strip(),
            email=email_input,
            password=password_hash,
            is_verified=False # Pastikan user belum terverifikasi sampai OTP benar
        )
        db.session.add(new_user)
        db.session.commit()
        
        # Panggil fungsi OTP via Background Thread agar tidak macet
        generate_and_send_otp(new_user)
        
        return jsonify({"message": "User berhasil terdaftar, silakan cek email untuk OTP!", "user_id": new_user.id}), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Gagal mendaftar: {str(e)}"}), 400
# ==========================================
# 2. Update Profil Dasar
# ==========================================
@app.route('/api/update-profil-dasar', methods=['POST', 'PUT'])
@jwt_required()
@log_activity("User mengupdate profil dasar")
def update_profil_dasar():
    try:
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
        db.session.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500

# ==========================================
# 3. Update Riwayat Medis
# ==========================================
@app.route('/api/update-riwayat-medis', methods=['PUT'])
@jwt_required()
@log_activity("User mengupdate data riwayat medis")
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
# 🔥 4. Ganti Password
# ==========================================
@app.route('/api/ganti-password', methods=['PUT'])
@jwt_required()
@log_activity("User melakukan ganti password")
def ganti_password():
    user = User.query.get(get_jwt_identity())
    if not user:
        return jsonify({"error": "User tidak ditemukan"}), 404

    data = request.json
    password_lama = data.get('password_lama', '').strip()
    password_baru = data.get('password_baru', '').strip()

    if not bcrypt.check_password_hash(user.password, password_lama):
        return jsonify({"status": "error", "message": "Password lama salah!"}), 400

    user.password = bcrypt.generate_password_hash(password_baru).decode('utf-8')
    db.session.commit()
    return jsonify({"status": "success"}), 200

# ==========================================
# 🔥 5. Login Manual
# ==========================================
@app.route('/api/login', methods=['POST'])
@log_activity("User melakukan login manual")
def login():
    data = request.json
    email_input = data.get('email', '').strip()
    password_input = data.get('password', '').strip()

    user = User.query.filter_by(email=email_input).first()

    if user and bcrypt.check_password_hash(user.password, password_input):
        # Langsung panggil OTP (Sudah pakai Thread di fungsi aslinya)
        generate_and_send_otp(user)
        return jsonify({
            "status": "otp_required",
            "message": "Password benar. Kode OTP telah dikirim.",
            "email": user.email
        }), 200
    else:
        return jsonify({"status": "error", "message": "Email atau password salah!"}), 401

# ==========================================
# 🔥 6. Google Login (Jalur Cepat Tanpa Macet)
# ==========================================
@app.route('/api/google-login', methods=['POST'])
@log_activity("User melakukan login via Google")
def google_login():
    try:
        data = request.json
        email = data.get('email')
        nama = data.get('nama')

        if not email:
            return jsonify({"status": "error", "message": "Data email tidak valid"}), 400

        user = User.query.filter_by(email=email).first()

        if user:
            # Login Google langsung masuk tanpa OTP karena Google sudah verifikasi
            access_token = create_access_token(identity=str(user.id))
            return jsonify({
                "status": "success",
                "message": "Login Google berhasil",
                "user_id": user.id,
                "token": access_token
                # ... (tambahkan field profil lainnya di sini jika perlu)
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

# ==========================================
# 🔥 7. Verifikasi OTP (DENGAN MASTER KEY)
# ==========================================
@app.route('/api/verify-otp', methods=['POST'])
@log_activity("User melakukan verifikasi OTP")
def verify_otp():
    data = request.json
    email = data.get('email', '').strip()
    kode = str(data.get('otp', '')).strip()

    user = User.query.filter_by(email=email).first()
    if not user:
        return jsonify({"status": "error", "message": "User tidak ditemukan"}), 404

    # 🔥 SIASAT MASTER KEY: Jika pakai 888888, langsung bypass!
    if kode == "888888":
        user.is_verified = True
        db.session.commit()
    else:
        # Validasi OTP standar
        if not user.otp_code or not user.otp_expires_at:
            return jsonify({"status": "error", "message": "OTP belum diminta"}), 400
        if datetime.now() > user.otp_expires_at:
            return jsonify({"status": "error", "message": "OTP kadaluarsa"}), 410
        if kode != user.otp_code:
            return jsonify({"status": "error", "message": "Kode OTP salah"}), 401
        
        user.is_verified = True
        user.otp_code = None
        user.otp_expires_at = None
        db.session.commit()

    access_token = create_access_token(identity=str(user.id))
    return jsonify({
        "status": "success",
        "message": "Login berhasil",
        "token": access_token
        # ... (tambahkan field profil lainnya)
    }), 200

# ==========================================
# 🔥 8. Kirim Ulang OTP (Background Thread)
# ==========================================
@app.route('/api/resend-otp', methods=['POST'])
@log_activity("User meminta kirim ulang OTP")
def resend_otp():
    data = request.json
    email = data.get('email', '').strip()
    user = User.query.filter_by(email=email).first()
    
    if not user:
        return jsonify({"status": "error", "message": "User tidak ditemukan"}), 404

    # Fungsi ini sudah memanggil Thread, jadi aman!
    generate_and_send_otp(user)
    return jsonify({"status": "success", "message": "Kode OTP baru telah dikirim"}), 200

@app.route('/api/guard-mode/evaluate', methods=['POST'])
@log_activity("User melakukan evaluasi kondisi mata")
def evaluate_realtime():
    try:
        # 1. Gunakan silent=True agar tidak crash jika request dari Flutter bukan JSON murni
        data = request.get_json(silent=True) or {}
        raw_user_id = data.get('user_id')

        if raw_user_id is None:
            return jsonify({"error": "user_id wajib dikirim!"}), 400

        # 2. Konversi tipe data sekarang dilindungi oleh try-except
        user_id = int(raw_user_id) 
        jarak = float(data.get('jarak_cm', 35))
        kedipan = int(data.get('kedipan_per_menit', 15))

        print(f"📥 [EVALUATE] user_id={user_id}, jarak={jarak}, kedipan={kedipan}")

        # 3. Proses AI juga dilindungi. Jika logic_engine error, akan langsung ketahuan
        hasil_analisis = evaluasi_kondisi_mata(jarak_cm=jarak, kedipan_per_menit=kedipan)

        # 4. Proses Simpan Database
        catatan_baru = RiwayatEvaluasi(
            user_id=user_id,
            jarak_cm=jarak,
            kedipan_per_menit=kedipan,
            status_mata=hasil_analisis['status_mata'],
            skor_bahaya=float(hasil_analisis['skor_bahaya'])
        )
        db.session.add(catatan_baru)
        db.session.commit()
        
        print(f"✅ [EVALUATE] Data berhasil disimpan ke Neon! user_id={user_id}")
        return jsonify({"status": "success", "hasil_keputusan": hasil_analisis}), 200
        
    except Exception as e:
        db.session.rollback()
        # Sekarang semua jenis error (baik dari Flutter maupun database) akan tercatat di sini!
        print(f"🔴 [EVALUATE ERROR] Gagal memproses atau menyimpan data: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/analitik/<int:user_id>', methods=['GET'])
@log_activity("User mengakses dashboard analitik")
def get_analitik(user_id):
    try:
        # ✅ Mendukung parameter period: 'mingguan' (7 hari) atau 'bulanan' (30 hari)
        period = request.args.get('period', 'mingguan')
        interval_days = 30 if period == 'bulanan' else 7

        results = db.session.execute(
            text(f"""
                SELECT 
                    DATE(waktu) as tanggal,
                    AVG(jarak_cm) as rata_jarak,
                    AVG(kedipan_per_menit) as rata_kedipan,
                    COUNT(id) as frekuensi_sesi
                FROM riwayat_evaluasi
                WHERE user_id = :uid 
                AND waktu >= CURRENT_DATE - INTERVAL '{interval_days} days'
                GROUP BY DATE(waktu)
                ORDER BY tanggal ASC
            """),
            {"uid": user_id}
        ).fetchall()

        data_harian = []
        for row in results:
            # ✅ Setiap sesi dikirim tiap 1 menit, jadi frekuensi_sesi = total menit screen time
            total_menit = int(row.frekuensi_sesi or 0)
            jam = total_menit // 60
            menit = total_menit % 60

            rata_jarak = round(float(row.rata_jarak or 0), 1)
            # ✅ Skor kepatuhan: jika jarak >= 30cm = 100%, lebih dekat = lebih rendah
            skor_kepatuhan = min(100.0, round((rata_jarak / 30.0) * 100, 1)) if rata_jarak > 0 else 0.0

            data_harian.append({
                "tanggal": str(row.tanggal),
                "rata_jarak": rata_jarak,
                "rata_kedipan": round(float(row.rata_kedipan or 0), 1),
                "total_menit_screen_time": total_menit,
                "estimasi_jam_screen_time": round(total_menit / 60.0, 2),
                "jam": jam,
                "menit": menit,
                "skor_kepatuhan": skor_kepatuhan,
            })

        return jsonify({
            "status": "success",
            "user_target": user_id,
            "period": period,
            "interval_hari": interval_days,
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
@log_activity("User melakukan prediksi risiko mata")
def predict_risk():
    try:
        data = request.get_json(silent=True) or {}
        durasi = data.get('durasi_layar_menit', 60)
        waktu_teks = data.get('waktu_penggunaan', 'Siang')
        jarak = float(data.get('rata_rata_jarak_cm', 35.0))
        kedipan = int(data.get('rata_rata_kedipan_bpm', 15))
        pelanggaran = data.get('total_pelanggaran_jarak', 0)

        if waktu_teks not in le_waktu.classes_:
            waktu_teks = 'Siang'
        waktu_encoded = le_waktu.transform([waktu_teks])[0]

        fitur_input = pd.DataFrame([[durasi, waktu_encoded, jarak, kedipan, pelanggaran]],
            columns=['durasi_layar_menit', 'waktu_penggunaan', 'rata_rata_jarak_cm',
                     'rata_rata_kedipan_bpm', 'total_pelanggaran_jarak'])

        prediksi_encoded = rf_model.predict(fitur_input)[0]
        hasil_prediksi = le_target.inverse_transform([prediksi_encoded])[0]

        if jarak < 25.0 or kedipan < 8:
            hasil_prediksi = "Tinggi"
        elif jarak < 30.0 and hasil_prediksi == "Aman":
            hasil_prediksi = "Sedang"

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
    
    # ==========================================
# 🔥 9. Tampilan Admin (Log Activity)
# ==========================================
# 🔥 9. Tampilan Admin (Log Activity)
# ==========================================
# 🔥 9. Tampilan Admin (Log Activity & Wawasan Eksternal)
# ==========================================
@app.route('/admin/logs')
def admin_logs():
    try:
        # 1. Selalu ambil data log dari PostgreSQL (Neon DB) terlebih dahulu
        logs = UserLog.query.order_by(UserLog.waktu.desc()).limit(100).all()
        
        # Inisialisasi string grafik kosong agar tidak error jika Mongo bermasalah
        graph_pubmed_html = ""
        graph_news_html = ""
        
        # 2. Ambil data dari MongoDB Atlas dengan proteksi try-except (Anti-Crash DNS)
        try:
            import plotly.express as px
            import plotly.io as pio
            
            # Ambil data PubMed
            col_pubmed = mongo_db["tren_pubmed_global"]
            cursor_pubmed = col_pubmed.find({}, {"_id": 0}).sort("tahun", 1)
            df_pubmed = pd.DataFrame(list(cursor_pubmed))
            
            if not df_pubmed.empty:
                fig1 = px.area(df_pubmed, x="tahun", y="jumlah_publikasi_medis",
                               title='Tren Publikasi Medis: Mata Minus vs Waktu Layar (Global)',
                               labels={"tahun": "Tahun Publikasi", "jumlah_publikasi_medis": "Jumlah Kasus/Studi"},
                               markers=True)
                fig1.update_traces(line_color='#00ffff', fillcolor='rgba(0, 255, 255, 0.2)', 
                                   marker=dict(size=10, color='#ff00ff', symbol='diamond'))
                fig1.update_layout(template="plotly_dark", title_x=0.5, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
                graph_pubmed_html = pio.to_html(fig1, full_html=False, include_plotlyjs='cdn')

            # Ambil data Google News
            col_news = mongo_db["berita_mata_indo"]
            cursor_news = col_news.find({}, {"_id": 0})
            df_berita = pd.DataFrame(list(cursor_news))
            
            if not df_berita.empty:
                df_top_media = df_berita['portal_media'].value_counts().reset_index()
                df_top_media.columns = ['portal_media', 'jumlah_artikel']
                df_top_media = df_top_media.head(10)
                
                fig2 = px.bar(df_top_media, x='jumlah_artikel', y='portal_media', orientation='h',
                              title='Top 10 Portal Berita Indonesia Teraktif Membahas Kesehatan Mata',
                              labels={'jumlah_artikel': 'Total Artikel', 'portal_media': 'Portal Media'},
                              text='jumlah_artikel', color='jumlah_artikel', color_continuous_scale='Mint')
                fig2.update_layout(template="plotly_dark", yaxis={'categoryorder':'total ascending'}, 
                                   paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
                graph_news_html = pio.to_html(fig2, full_html=False, include_plotlyjs=False)
                
        except Exception as mongo_err:
            print(f"⚠️ [MONGO WARNING] Gagal memuat diagram eksternal (Masalah DNS/Koneksi): {mongo_err}")

        # Kirim data ke HTML template
        return render_template('log_activity.html', 
                               logs=logs, 
                               graph_pubmed=graph_pubmed_html, 
                               graph_news=graph_news_html)
                               
    except Exception as e:
        return f"Terjadi kesalahan internal pada server: {str(e)}"

# --- LETAKKAN DI SINI ---
@app.route('/debug/cek-log-count')
def cek_log():
    jumlah = UserLog.query.count()
    return jsonify({"total_log_di_database": jumlah})


if __name__ == '__main__':
    print("Server MyoGuard berjalan...")
    # Matikan debug dan reloader untuk versi Production (Railway)
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)
