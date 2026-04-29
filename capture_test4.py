from picamera2 import Picamera2
import time
import cv2
import numpy as np
from flask import Flask, Response, render_template_string
import threading
import os
import glob

# ---------------- CAMERA SETUP ----------------
picam2 = Picamera2()
resolution = (320, 240)
picam2.configure(
    picam2.create_preview_configuration(
        main={"format": "XRGB8888", "size": resolution}
    )
)
picam2.start()
time.sleep(0.1)  # camera warmup

# ---------------- FLASK APP ----------------
app = Flask(__name__)

INDEX_HTML = """
<!doctype html>
<html>
<head>
    <title>Pi Circle Detector</title>
    <style>
        body { font-family: Arial, sans-serif; background:#111; color:#eee; text-align:center; }
        img { border: 2px solid #555; margin:10px; }
        h2 { color: #aaa; margin-top: 40px; border-top: 1px solid #333; padding-top: 20px; }
        .gallery { display: flex; flex-wrap: wrap; justify-content: center; }
        .gallery div { margin:10px; border:2px solid #555; padding:10px; }
        .gallery p { margin: 0 0 5px 0; font-size: 0.85em; color: #aaa; }
    </style>
</head>
<body>
    <h1>Pi Dark Circle Detector</h1>
    <p>Green outline = detected dark circle. Red dot = center point.</p>

    <!-- LIVE STREAM -->
    <h2>Live Feed</h2>
    <img src="{{ url_for('video_feed') }}" width="640">

    <!-- CAPTURED IMAGES GALLERY -->
    <h2>Captured Images</h2>
    <p><a href="javascript:location.reload()" style="color:#aaa;">Refresh to see new captures</a></p>
    <div class="gallery">
        {% for f in files %}
        <div>
            <p>{{ f }}</p>
            <img src="/captured/{{ f }}" width="320">
        </div>
        {% endfor %}
        {% if not files %}
        <p>No images captured yet.</p>
        {% endif %}
    </div>
</body>
</html>
"""

@app.route("/")
def index():
    captured_path = "/home/pi/Desktop/Final/captured"
    if os.path.exists(captured_path):
        files = sorted(
            [f for f in os.listdir(captured_path) if f.endswith(".jpg")],
            key=lambda x: int(x.split("_")[1].split(".")[0])
        )
    else:
        files = []
    return render_template_string(INDEX_HTML, files=files)

def gen_frames():
    """
    Generator that grabs frames from Picamera2, applies Hough Circle Transform
    to detect dark circles, draws markers on them, encodes as JPEG,
    and yields as MJPEG stream.
    """ 
    while True:
        # Capture frame as NumPy array
        frame = picam2.capture_array()

        # Convert to BGR for OpenCV
        frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)

        # Blur to reduce noise before circle detection
        blurred = cv2.GaussianBlur(gray, (15, 15), 2)

        # Detect circles using Hough Circle Transform
        circles = cv2.HoughCircles(
            blurred,
            cv2.HOUGH_GRADIENT,
            dp=1,
            minDist=20,       # minimum distance between circle centers
            param1=50,        # edge detection sensitivity
            param2=20,        # circle detection threshold (lower = more circles)
            minRadius=5,      # smallest circle to detect (pixels)
            maxRadius=40      # largest circle to detect (pixels)
        )

        # Draw markers only on dark circles
        if circles is not None:
            circles = np.uint16(np.around(circles))
            for c in circles[0, :]:
                cx, cy, r = c[0], c[1], c[2]
                roi = gray[max(0, cy-r):cy+r, max(0, cx-r):cx+r]
                if roi.size > 0 and np.mean(roi) < 110:
                    cv2.circle(frame_bgr, (cx, cy), r, (0, 255, 0), 2)  # green outline
                    cv2.circle(frame_bgr, (cx, cy), 2, (0, 0, 255), 3)  # red center dot

        # Encode the annotated frame as JPEG and yield
        ret, jpeg = cv2.imencode(".jpg", frame_bgr)
        if not ret:
            continue
        yield (b"--frame\r\n"
               b"Content-Type: image/jpeg\r\n\r\n" + jpeg.tobytes() + b"\r\n")

@app.route("/video_feed")
def video_feed():
    return Response(
        gen_frames(),
        mimetype="multipart/x-mixed-replace; boundary=frame",
    )

@app.route("/captured/<filename>")
def captured_image(filename):
    filepath = os.path.join("/home/pi/Desktop/Final/captured", filename)
    with open(filepath, "rb") as f:
        image_data = f.read()
    return Response(image_data, mimetype="image/jpeg")

# ---------------- TIMED CAPTURE & LOCAL SAVE ----------------
def capture_and_upload():
    os.makedirs("/home/pi/Desktop/Final/captured", exist_ok=True)

    old_files = glob.glob("/home/pi/Desktop/Final/captured/*.jpg")
    for f in old_files:
        os.remove(f)

    duration = 120
    interval = 3
    captures = duration // interval

    print(f"Starting capture: {captures} images over {duration} seconds")
    print("Old captures cleared.")

    for i in range(captures):
        # Capture frame
        frame = picam2.capture_array()
        frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)

        # Run circle detection so saved image has annotations
        blurred = cv2.GaussianBlur(gray, (15, 15), 2)
        circles = cv2.HoughCircles(
            blurred,
            cv2.HOUGH_GRADIENT,
            dp=1,
            minDist=20,
            param1=50,
            param2=20,
            minRadius=5,
            maxRadius=40
        )
        if circles is not None:
            circles = np.uint16(np.around(circles))
            for c in circles[0, :]:
                cx, cy, r = c[0], c[1], c[2]
                roi = gray[max(0, cy-r):cy+r, max(0, cx-r):cx+r]
                if roi.size > 0 and np.mean(roi) < 110:
                    cv2.circle(frame_bgr, (cx, cy), r, (0, 255, 0), 2)
                    cv2.circle(frame_bgr, (cx, cy), 2, (0, 0, 255), 3)

        # Save locally with annotations
        filename = f"/home/pi/Desktop/Final/captured/capture_{i+1}.jpg"
        cv2.imwrite(filename, frame_bgr)
        print(f"Capture {i+1}/{captures} saved to {filename}")

        time.sleep(interval)

    print("Capture session complete.")

# ---------------- MAIN ----------------
if __name__ == "__main__":
    try:
        # Start capture in background thread so Flask still runs
        upload_thread = threading.Thread(target=capture_and_upload, daemon=True)
        upload_thread.start()

        app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
    finally:
        picam2.stop()