import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import LabelEncoder
from sklearn.metrics import accuracy_score, classification_report
import joblib

# 1. Load Dataset
df = pd.read_csv('dataset_myoguard.csv')
print("Dataset berhasil dimuat!")

# 2. Preprocessing (Ubah teks jadi angka agar AI paham)
le_waktu = LabelEncoder()
df['waktu_penggunaan'] = le_waktu.fit_transform(df['waktu_penggunaan'])

le_target = LabelEncoder()
df['tingkat_risiko_kelelahan'] = le_target.fit_transform(df['tingkat_risiko_kelelahan'])

# Pisahkan Fitur (X) dan Target (y)
X = df.drop('tingkat_risiko_kelelahan', axis=1)
y = df['tingkat_risiko_kelelahan']

# 3. Bagi data untuk Belajar (80%) dan data untuk Ujian (20%)
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

# 4. Inisialisasi & Latih Model Random Forest
print("Sedang melatih model... Mohon tunggu...")
model = RandomForestClassifier(n_estimators=100, random_state=42)
model.fit(X_train, y_train)

# 5. Evaluasi Hasil Belajar
y_pred = model.predict(X_test)
akurasi = accuracy_score(y_test, y_pred)

print(f"\n--- HASIL PELATIHAN ---")
print(f"Akurasi Model: {akurasi * 100:.2f}%")
print("\nLaporan Detail:")
print(classification_report(y_test, y_pred, target_names=le_target.classes_))

# 6. Simpan "Otak" AI agar bisa dipakai di Flask
joblib.dump(model, 'myoguard_model.pkl')
joblib.dump(le_waktu, 'le_waktu.pkl')
joblib.dump(le_target, 'le_target.pkl')

print("\nSukses! Model AI telah disimpan sebagai 'myoguard_model.pkl'")