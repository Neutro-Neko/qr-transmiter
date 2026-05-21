import cv2
import numpy as np
import qrcode
import base64
import subprocess
import sys
import threading
from queue import Queue, Empty

scanner_proc = None
qr_queue = Queue()

MAX_SIZE = 300
SAVE_EVERY = 10

MODE = "receive"
INPUT = "shrek.txt"
OUTPUT = "output"


def encode_frame(frame_type, seq=0, data=""):
    return f"{frame_type}|{seq}|{data}"


def decode_frame(text):
    try:
        frame_type, seq, data = text.split("|", 2)
        return frame_type, int(seq), data
    except:
        return None, None, None


def chunk(data, size):
    seq = 1
    for i in range(0, len(data), size):
        yield seq, data[i:i + size]
        seq += 1


def enqueue_output(out, queue):
    try:
        for line in iter(out.readline, ''):
            if not line:
                break
            queue.put(line)
    except Exception:
        pass
    finally:
        out.close()


def read_frame():
    global scanner_proc
    if scanner_proc is None:
        scanner_proc = subprocess.Popen(
            ['./qr_scanner'],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1
        )
        t = threading.Thread(target=enqueue_output, args=(scanner_proc.stdout, qr_queue))
        t.daemon = True
        t.start()
    
    while True:
        if scanner_proc.poll() is not None:
            raise RuntimeError("QR Scanner subprocess exited unexpectedly")
        try:
            line = qr_queue.get_nowait()
            data = line.strip()
            if data:
                print(data)
                return data
        except Empty:
            cv2.waitKey(1)
            import time
            time.sleep(0.01)


def wait_for_type(frame_type):
    while True:
        data = read_frame()
        t, seq, payload = decode_frame(data)

        if t == frame_type:
            return t, seq, payload


def wait_for_ack(seq):
    while True:
        t, rseq, _ = wait_for_type("ACK")
        if rseq == seq:
            return


def generate(data):
    qr = qrcode.QRCode(box_size=10, border=1)
    qr.add_data(data)
    qr.make(fit=True)

    img = qr.make_image(fill_color=0)
    img = np.array(img, dtype=np.uint8)

    img = cv2.resize(img, (800, 800), cv2.INTER_NEAREST)

    cv2.imshow("QR", img)
    cv2.waitKey(1)


def safe_b64decode(data):
    missing = len(data) % 4
    if missing:
        data += "=" * (4 - missing)
    return base64.b64decode(data.encode())


def sender(data, file_name):
    generate(encode_frame("START", 0, file_name))
    wait_for_type("START")

    for seq, part in chunk(data, MAX_SIZE):
        generate(encode_frame("DATA", seq, part))
        wait_for_ack(seq)

    generate(encode_frame("END", seq, ""))


def receiver():
    buffer = ""
    seq = 1
    chunk_count = 0

    _, _, file_name = wait_for_type("START")

    temp_file = f"{OUTPUT}.tmp"

    with open(temp_file, "wb") as f:
        while True:
            raw = read_frame()
            frame_type, recived_seq, recived_data = decode_frame(raw)

            if frame_type == "END":
                if buffer:
                    f.write(safe_b64decode(buffer))
                break

            if frame_type == "DATA" and recived_seq == seq:
                buffer += recived_data
                seq += 1
                chunk_count += 1

                generate(encode_frame("ACK", recived_seq, ""))

                if chunk_count >= SAVE_EVERY:
                    f.write(safe_b64decode(buffer))
                    buffer = ""
                    chunk_count = 0

        return file_name, temp_file


if MODE == "send":
    with open(INPUT, "rb") as f:
        data = base64.b64encode(f.read()).decode()

    sender(data, INPUT)

elif MODE == "receive":
    file_name, temp_file = receiver()

    with open(file_name or OUTPUT, "wb") as out:
        with open(temp_file, "rb") as inp:
            out.write(inp.read())

if scanner_proc is not None:
    scanner_proc.terminate()
    scanner_proc.wait()
cv2.destroyAllWindows()