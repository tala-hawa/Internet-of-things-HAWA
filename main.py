from machine import Pin, ADC
import time
import math

# ======== Setup ===========
vrx = ADC(Pin(34))
vry = ADC(Pin(35))
btn = Pin(32, Pin.IN, Pin.PULL_UP)
led = Pin(2, Pin.OUT)       # GPIO 2 — built-in LED on most ESP32 boards

vrx.atten(ADC.ATTN_11DB)
vry.atten(ADC.ATTN_11DB)

# ======== Configuration ===========
IDLE_LIMIT     = 60     # Seconds before program stops
IDLE_THRESHOLD = 50     # ADC units — movement smaller than this = idle
SPEED_LIMIT    = 10    # ADC units/sec — LED turns on above this

print("Joystick started...")

# ======== Track idle time and speed ===========
last_move_time = time.time()
prev_x         = vrx.read()
prev_y         = vry.read()
prev_time      = time.time()

# ======== Main loop ===========
while True:
    x      = vrx.read()
    y      = vry.read()
    button = 1 if btn.value() == 0 else 0

    # ======== Calculate speed ===========
    now   = time.time()
    dt    = now - prev_time
    speed = math.sqrt((x - prev_x)**2 + (y - prev_y)**2) / dt if dt > 0 else 0.0

    # ======== LED on if speed exceeds limit ===========
    if speed > SPEED_LIMIT:
        led.value(1)    # LED ON
    else:
        led.value(0)    # LED OFF

    # ======== Check for movement ===========
    dx = abs(x - prev_x)
    dy = abs(y - prev_y)

    if dx > IDLE_THRESHOLD or dy > IDLE_THRESHOLD or button == 1:
        last_move_time = time.time()   # Reset idle timer

    # ======== Check if idle too long ===========
    idle_seconds = time.time() - last_move_time
    if idle_seconds >= IDLE_LIMIT:
        led.value(0)    # Make sure LED is off when stopping
        print("Joystick idle for 60 seconds. Stopping.")
        break

    # ======== Send data over serial ===========
    print(f"{x},{y},{button}")

    prev_x    = x
    prev_y    = y
    prev_time = now
    time.sleep(0.06)
