import sqlite3

conn = sqlite3.connect('db.sqlite3')
conn.row_factory = sqlite3.Row

# Check what parent_generation_id the audio gen has
audio_gen = conn.execute("SELECT id, parent_generation_id, status, created_at FROM generations_generation WHERE id = 'e3462064c5964bd7b41a8207d5d2a14b'").fetchone()
print("AUDIO GEN:")
if audio_gen:
    print(dict(audio_gen))

# Check Esse/Kwame voice profile
voice = conn.execute("SELECT * FROM voices_voiceprofile WHERE id = '1012811ecd2143319ecbd6f8e2682729'").fetchone()
print("\nVOICE PROFILE:")
if voice:
    for k,v in dict(voice).items():
        print(f"  {k}: {repr(v)}")

# Check all children of the video gen
children = conn.execute("SELECT id, generation_type, status, model_id_snapshot, parent_generation_id FROM generations_generation WHERE parent_generation_id = '5379b86598804cada7a2deb3ca782f6e'").fetchall()
print(f"\nCHILDREN OF VIDEO GEN ({len(children)}):")
for c in children:
    print(dict(c))
    
# Check the Wan video model
model = conn.execute("SELECT * FROM providers_aimodel WHERE id = 14").fetchone()
if model:
    print("\nVIDEO MODEL:")
    for k,v in dict(model).items():
        print(f"  {k}: {repr(v)}")
