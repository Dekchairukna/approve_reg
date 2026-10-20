"""เปิดระบบ:  python3 app.py   (ค่าเริ่มต้นพอร์ต 8000 ตั้งเองได้ด้วย PORT=...)"""
import os
import socket
import sys

from checkin import create_app

app = create_app()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    with socket.socket() as s:
        if s.connect_ex(('127.0.0.1', port)) == 0:
            sys.exit(f'พอร์ต {port} มีโปรแกรมอื่นใช้อยู่ ลองใช้พอร์ตอื่น เช่น  PORT=8080 python3 app.py')
    print(f'ระบบพร้อมใช้งานที่ http://localhost:{port}   หลังบ้านเจ้าหน้าที่: http://localhost:{port}/admin')
    print('กด Ctrl+C เพื่อปิดระบบ')
    try:
        from waitress import serve
        serve(app, host='0.0.0.0', port=port, threads=8)
    except ImportError:
        app.run(host='0.0.0.0', port=port)
