import csv
import random

def buat_dataset(jumlah_baris=1000):
    # Header kolom untuk file CSV
    header = [
        'durasi_layar_menit', 
        'waktu_penggunaan', 
        'rata_rata_jarak_cm', 
        'rata_rata_kedipan_bpm', 
        'total_pelanggaran_jarak', 
        'tingkat_risiko_kelelahan'
    ]
    
    data = []
    
    for _ in range(jumlah_baris):
        # 1. Generate Fitur (X) secara acak tapi realistis
        durasi = random.randint(15, 240) # Sesi dari 15 menit sampai 4 jam
        waktu = random.choice(["Pagi", "Siang", "Malam"])
        jarak = random.uniform(20.0, 65.0) # Jarak 20cm sampai 65cm
        kedipan = random.randint(5, 25) # Normalnya manusia berkedip 15-20x per menit
        
        # Logika jumlah pelanggaran bergantung pada rata-rata jarak
        if jarak < 30:
            pelanggaran = random.randint(30, 100)
        elif jarak < 40:
            pelanggaran = random.randint(10, 35)
        else:
            pelanggaran = random.randint(0, 10)
            
        # 2. Logika Medis Tersembunyi (Menentukan Label Target)
        poin_risiko = 0
        
        # Durasi main laptop terlalu lama = risiko naik
        if durasi > 120: poin_risiko += 2
        elif durasi > 60: poin_risiko += 1
        
        # Jarak terlalu dekat = risiko naik drastis
        if jarak < 33: poin_risiko += 3
        elif jarak < 45: poin_risiko += 1
        
        # Jarang kedip (indikasi mata kering) = risiko naik drastis
        if kedipan < 10: poin_risiko += 3
        elif kedipan < 15: poin_risiko += 1
        
        # Banyak melanggar = risiko naik
        if pelanggaran > 40: poin_risiko += 2
        
        # Main malam hari = tambah sedikit risiko (karena cahaya layar)
        if waktu == "Malam": poin_risiko += 1
        
        # 3. Penentuan Label (Target Y) berdasarkan total poin
        if poin_risiko >= 7:
            label = "Tinggi"
        elif poin_risiko >= 4:
            label = "Sedang"
        else:
            label = "Rendah"
            
        data.append([durasi, waktu, round(jarak, 2), kedipan, pelanggaran, label])
        
    return header, data

# Proses pembuatan dan penyimpanan file CSV
print("Memulai proses cetak dataset...")
header, dataset_dummy = buat_dataset(1000)

nama_file = 'dataset_myoguard.csv'
with open(nama_file, mode='w', newline='') as file:
    writer = csv.writer(file)
    writer.writerow(header)
    writer.writerows(dataset_dummy)

print(f"Sukses! {len(dataset_dummy)} baris data telah disimpan di file '{nama_file}'")