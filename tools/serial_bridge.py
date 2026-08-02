"""파이용 TCP <-> 시리얼 브리지 (자동 복구). IO 테스트 패널이 노트북에서 접속.

- 시리얼 포트가 사라지면(USB 재열거) by-id 로 다시 찾아 재오픈 → USB 튐 자동 복구.
- 소켓 클라이언트는 유지; 시리얼만 밑에서 재오픈.
사용: python serial_bridge.py [20108]
주의: 키오스크 서비스는 먼저 stop (포트 점유 충돌 방지).
"""
import glob, os, socket, sys, time
import serial

TCP = int(sys.argv[1]) if len(sys.argv) > 1 else 20108


def find_port():
    g = glob.glob("/dev/serial/by-id/*CP210*") or glob.glob("/dev/ttyUSB*")
    return g[0] if g else None


def open_serial():
    while True:
        p = find_port()
        if p:
            try:
                s = serial.Serial(p, 9600, bytesize=8, parity="N", stopbits=1, timeout=0.05)
                print("serial open:", p, flush=True)
                return s
            except Exception as e:  # noqa: BLE001
                print("serial open fail:", e, flush=True)
        time.sleep(1.0)


srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
srv.bind(("0.0.0.0", TCP))
srv.listen(1)
print(f"bridge listening on {TCP}", flush=True)

ser = open_serial()
while True:
    conn, addr = srv.accept()
    print("client connected:", addr, flush=True)
    conn.settimeout(0.05)
    try:
        while True:
            # 시리얼 → 소켓 (시리얼 오류 시 재오픈, 소켓은 유지)
            try:
                d = ser.read(256)
                if d:
                    conn.sendall(d)
            except (serial.SerialException, OSError) as e:
                print("serial read err, reopen:", e, flush=True)
                try: ser.close()
                except Exception: pass
                ser = open_serial()
                continue
            # 소켓 → 시리얼
            try:
                c = conn.recv(256)
                if c == b"":
                    break
                if c:
                    try:
                        ser.write(c)
                    except (serial.SerialException, OSError) as e:
                        print("serial write err, reopen:", e, flush=True)
                        try: ser.close()
                        except Exception: pass
                        ser = open_serial()
            except socket.timeout:
                pass
    except (ConnectionError, OSError):
        pass
    finally:
        conn.close()
        print("client disconnected", flush=True)
