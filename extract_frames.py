import os
import cv2

video_path = r"media/uploads/6/video/50fb9df1172d.mp4"
output_dir = r"C:\Users\HP\.gemini\antigravity-ide\brain\45ac726d-fdc4-4e1a-a545-12f02aa1fc6d"

cap = cv2.VideoCapture(video_path)
total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
fps = cap.get(cv2.CAP_PROP_FPS)
width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
duration = total_frames / fps if fps > 0 else 0

print(f"Video Info: {width}x{height}, {fps} fps, {total_frames} frames, {duration:.2f}s")

# Extract 4 sample frames: 0%, 25%, 50%, 75%
frame_indices = [0, int(total_frames * 0.25), int(total_frames * 0.5), int(total_frames * 0.75)]
extracted = []

for idx in frame_indices:
    cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
    ret, frame = cap.read()
    if ret:
        out_name = f"video_5379_frame_{idx}.jpg"
        out_path = os.path.join(output_dir, out_name)
        cv2.imwrite(out_path, frame)
        extracted.append(out_path)
        print(f"Saved frame {idx} to {out_path}")
cap.release()
