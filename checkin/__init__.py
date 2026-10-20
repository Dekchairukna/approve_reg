"""ระบบยืนยันรายชื่อและรายงานตัวนักกีฬา (Flask + PostgreSQL/SQLite)"""
import os
import secrets
from datetime import timedelta

from flask import Flask, jsonify, request

from . import admin, auth, public
from .db import close_db, database_target, init_db

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _secret_key(instance_dir):
    if os.environ.get('SECRET_KEY'):
        return os.environ['SECRET_KEY']
    path = os.path.join(instance_dir, 'secret_key')
    if not os.path.exists(path):
        with open(path, 'w') as f:
            f.write(secrets.token_hex(32))
    with open(path) as f:
        return f.read().strip()


def create_app(instance_dir=None):
    instance_dir = instance_dir or os.environ.get('CHECKIN_DATA', os.path.join(BASE, 'instance'))
    os.makedirs(os.path.join(instance_dir, 'uploads'), exist_ok=True)
    app = Flask(__name__, static_folder=os.path.join(BASE, 'static'), static_url_path='/static')
    app.config.update(
        DATABASE=database_target(instance_dir),
        UPLOAD_DIR=os.path.join(instance_dir, 'uploads'),
        SECRET_KEY=_secret_key(instance_dir),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE='Lax',
        SESSION_COOKIE_SECURE=os.environ.get('COOKIE_SECURE') == '1',
        PERMANENT_SESSION_LIFETIME=timedelta(hours=12),
        MAX_CONTENT_LENGTH=20 * 1024 * 1024,
        JSON_AS_ASCII=False,
    )
    app.json.ensure_ascii = False
    init_db(app.config['DATABASE'], app.config['UPLOAD_DIR'])

    @app.before_request
    def before():
        # กัน CSRF: คำขอที่เปลี่ยนข้อมูลต้องมาจากหน้าเว็บของระบบเอง (ส่ง header นี้ได้เฉพาะ same-origin)
        if request.method in ('POST', 'PUT', 'DELETE') and request.path.startswith('/api/'):
            if request.headers.get('X-Requested-With') != 'checkin':
                return jsonify(error='คำขอไม่ถูกต้อง'), 400
        auth.load_user()

    @app.after_request
    def headers(resp):
        resp.headers.setdefault('X-Content-Type-Options', 'nosniff')
        resp.headers.setdefault('X-Frame-Options', 'SAMEORIGIN')
        resp.headers.setdefault('Referrer-Policy', 'same-origin')
        if request.path.startswith('/api/'):
            resp.headers.setdefault('Cache-Control', 'no-store')
        return resp

    @app.errorhandler(404)
    def not_found(_):
        if request.path.startswith('/api/'):
            return jsonify(error='ไม่พบข้อมูล'), 404
        return app.send_static_file('404.html'), 404

    @app.errorhandler(413)
    def too_large(_):
        return jsonify(error='ไฟล์ใหญ่เกิน 20 MB'), 413

    app.teardown_appcontext(close_db)
    app.register_blueprint(auth.bp)
    app.register_blueprint(public.bp)
    app.register_blueprint(admin.bp)
    return app
