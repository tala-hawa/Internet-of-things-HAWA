from flask import Flask, render_template
import json
import plotly
import plotly.subplots
import serial
import serial.tools.list_ports
import datetime
import math
import time

# ======== Configuration ===========
SERIAL_PORT  = '/dev/ttyACM0'
BAUD_RATE    = 115200
SPEED_LIMIT  = 10000
NUM_READINGS = 5        # Reduced from 10 to speed up response time

# ======== Initialize Flask app ===========
app = Flask(__name__)

# ======== Helper: auto-detect serial port ===========
def find_serial_port():
    ports = serial.tools.list_ports.comports()
    for p in ports:
        if 'ACM' in p.device or 'usbmodem' in p.device:
            return p.device
    return SERIAL_PORT

# ======== Helper: read N joystick readings from serial ===========
def read_joystick_data(n):
    data = {
        'timeT':  [],
        'x':      [],
        'y':      [],
        'speed':  [],
        'button': []
    }

    port = find_serial_port()

    try:
        ser = serial.Serial(port, BAUD_RATE, timeout=0.5)  # Reduced from 2s
        time.sleep(0.2)             # Let port stabilize
        ser.reset_input_buffer()    # Flush stale buffered data

        prev_x    = 32767
        prev_y    = 32767
        prev_time = datetime.datetime.now()
        collected = 0
        attempts  = 0

        while collected < n and attempts < n * 2:  # Reduced from n*3
            attempts += 1
            line  = ser.readline().decode('utf-8', errors='ignore').strip()
            parts = line.split(',')
            if len(parts) != 3:
                continue
            try:
                x, y, btn = int(parts[0]), int(parts[1]), int(parts[2])
            except ValueError:
                continue

            now   = datetime.datetime.now()
            dt    = (now - prev_time).total_seconds()
            speed = math.sqrt((x - prev_x)**2 + (y - prev_y)**2) / dt if dt > 0 else 0.0

            data['timeT'].append(now)
            data['x'].append(x)
            data['y'].append(y)
            data['speed'].append(round(speed, 1))
            data['button'].append(btn)

            prev_x, prev_y, prev_time = x, y, now
            collected += 1

        ser.close()

    except serial.SerialException as e:
        print(f"[WARN] Serial error: {e}")
        for i in range(n):
            data['timeT'].append(datetime.datetime.now() - datetime.timedelta(seconds=(n - i) * 0.1))
            data['x'].append(32767)
            data['y'].append(32767)
            data['speed'].append(0.0)
            data['button'].append(0)

    return data

# ======== Route: main page ===========
@app.route('/joystick')
def joystick():
    return render_template('joystick.html', speed_limit=SPEED_LIMIT)

# ======== Route: JSON data endpoint ===========
@app.route('/data')
def data():
    readings = read_joystick_data(NUM_READINGS)

    if not readings['x']:
        return json.dumps({
            'graphJSON':    None,
            'latest_x':     32767,
            'latest_y':     32767,
            'latest_speed': 0,
            'button':       0,
            'error':        'No data received from serial port'
        })

    fig = plotly.subplots.make_subplots(
        rows=2, cols=1,
        vertical_spacing=0.2,
        subplot_titles=('Joystick Position (X vs Y)', 'Speed Over Time')
    )

    fig['layout']['margin'] = {'l': 40, 'r': 20, 'b': 40, 't': 40}

    fig.append_trace({
        'x':      readings['x'],
        'y':      readings['y'],
        'mode':   'lines+markers',
        'type':   'scatter',
        'name':   'Position',
        'marker': {'color': 'blue'}
    }, 1, 1)

    time_strs = [t.strftime('%H:%M:%S') for t in readings['timeT']]
    fig.append_trace({
        'x':      time_strs,
        'y':      readings['speed'],
        'mode':   'lines+markers',
        'type':   'scatter',
        'name':   'Speed',
        'marker': {'color': 'green'}
    }, 2, 1)

    fig.append_trace({
        'x':    time_strs,
        'y':    [SPEED_LIMIT] * len(time_strs),
        'mode': 'lines',
        'type': 'scatter',
        'name': 'Speed Limit',
        'line': {'color': 'red', 'dash': 'dash'}
    }, 2, 1)

    fig.update_xaxes(title_text="X Position (ADC)", row=1, col=1)
    fig.update_yaxes(title_text="Y Position (ADC)", row=1, col=1)
    fig.update_xaxes(title_text="Time",             row=2, col=1)
    fig.update_yaxes(title_text="Speed (units/s)",  row=2, col=1)

    return json.dumps({
        'graphJSON':    json.loads(json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)),
        'latest_x':     readings['x'][-1],
        'latest_y':     readings['y'][-1],
        'latest_speed': readings['speed'][-1],
        'button':       readings['button'][-1],
    })


if __name__ == '__main__':
    print()
    print('=======================================================')
    print('Joystick Monitor — Flask + Plotly')
    print('http://0.0.0.0:5050/joystick')
    print('=======================================================')
    print()
    app.run(host="0.0.0.0", port=5050, debug=False)
