from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory, session
import os
import sqlite3
from datetime import datetime
from functools import wraps
from werkzeug.utils import secure_filename
from uuid import uuid4
from contextlib import closing

app = Flask(__name__, template_folder='templates')
# Clave secreta necesaria para manejar sesiones
app.secret_key = os.environ.get('SECRET_KEY', 'cambia-esta-clave-secreta-en-produccion')

# Credenciales de acceso
USUARIO_CORRECTO = "Normal Superior Claudina Munera"
PASSWORD_CORRECTO = "Normal2026*"

# Directorios de datos y base de datos
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'datos')
FILES_DIR = os.path.join(DATA_DIR, 'archivos')
BACKUP_DIR = os.path.join(DATA_DIR, 'backups')
DB_PATH = os.path.join(DATA_DIR, 'rdi.db')
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100 MB por archivo


def db_connect():
    """Abre SQLite con espera suficiente ante escrituras concurrentes."""
    conn = sqlite3.connect(DB_PATH, timeout=60)
    conn.execute('PRAGMA busy_timeout = 60000')
    conn.execute('PRAGMA foreign_keys = ON')
    return conn


def insert_compatible(conn, table, values):
    """Inserta usando las columnas reales, incluidas las obligatorias de esquemas previos."""
    info = conn.execute(f'PRAGMA table_info({table})').fetchall()
    columns = {row[1]: row for row in info}
    payload = dict(values)
    now = datetime.now().isoformat()

    owner_row = conn.execute('SELECT id FROM users ORDER BY id LIMIT 1').fetchone() if conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='users'").fetchone() else None
    defaults = {
        'owner_id': owner_row[0] if owner_row else 1,
        'created_at': now,
        'stored_name': payload.get('filename', ''),
        'mime': 'application/octet-stream',
        'size': 0,
        'share_token': uuid4().hex,
        'tags': '',
        'visibility': 'publico',
        'filename': payload.get('stored_name', ''),
    }
    for name, row in columns.items():
        not_null, default_value = row[3], row[4]
        if name not in payload and not_null and default_value is None and name != 'id':
            if name in defaults:
                payload[name] = defaults[name]

    selected = [(name, value) for name, value in payload.items() if name in columns]
    names = ', '.join(f'"{name}"' for name, _ in selected)
    placeholders = ', '.join('?' for _ in selected)
    conn.execute(f'INSERT INTO {table} ({names}) VALUES ({placeholders})',
                 [value for _, value in selected])

os.makedirs(FILES_DIR, exist_ok=True)
os.makedirs(BACKUP_DIR, exist_ok=True)

def init_db():
    conn = db_connect()
    conn.execute("PRAGMA journal_mode = WAL")
    cursor = conn.cursor()
    
    # Tabla de colecciones
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS collections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT
        )
    ''')
    
    # Tabla de archivos
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            original_name TEXT NOT NULL,
            filename TEXT NOT NULL,
            collection_id INTEGER,
            visibility TEXT DEFAULT 'publico',
            tags TEXT,
            created_at TEXT,
            FOREIGN KEY (collection_id) REFERENCES collections (id)
        )
    ''')
    
    # Migración automática si la tabla ya existía con esquema antiguo
    cursor.execute("PRAGMA table_info(files)")
    columns = [row[1] for row in cursor.fetchall()]
    
    if 'filename' not in columns:
        cursor.execute("ALTER TABLE files ADD COLUMN filename TEXT NOT NULL DEFAULT ''")
    if 'visibility' not in columns:
        cursor.execute("ALTER TABLE files ADD COLUMN visibility TEXT DEFAULT 'publico'")
    if 'tags' not in columns:
        cursor.execute("ALTER TABLE files ADD COLUMN tags TEXT")
    
    # Insertar colecciones iniciales si la tabla está vacía
    cursor.execute("SELECT COUNT(*) FROM collections")
    if cursor.fetchone()[0] == 0:
        insert_compatible(conn, 'collections', {'name': 'General', 'description': 'Colección por defecto'})
        insert_compatible(conn, 'collections', {'name': 'Guías de Aprendizaje', 'description': 'Recursos pedagógicos'})
        insert_compatible(conn, 'collections', {'name': 'Actas e Informes', 'description': 'Documentos institucionales'})
    
    conn.commit()
    conn.close()

init_db()

# Decorador para proteger rutas y exigir login
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            flash('Por favor inicia sesión para acceder al repositorio.', 'danger')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# RUTA DE LOGIN
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = request.form.get('usuario')
        password = request.form.get('password')
        
        if user == USUARIO_CORRECTO and password == PASSWORD_CORRECTO:
            session['logged_in'] = True
            session['user'] = user
            flash('¡Bienvenido al Repositorio Digital Institucional!', 'success')
            return redirect(url_for('index'))
        else:
            flash('Usuario o contraseña incorrectos.', 'danger')
            
    return render_template('login.html')

# RUTA DE LOGOUT
@app.route('/logout')
def logout():
    session.clear()
    flash('Has cerrado sesión correctamente.', 'success')
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    q = request.args.get('q', '').strip()
    conn = db_connect()
    cursor = conn.cursor()
    
    cursor.execute("SELECT id, name, description FROM collections")
    collections = [{'id': row[0], 'name': row[1], 'description': row[2]} for row in cursor.fetchall()]
    
    if q:
        cursor.execute('''
            SELECT f.id, f.original_name, f.filename, c.name, f.visibility, f.tags
            FROM files f
            LEFT JOIN collections c ON f.collection_id = c.id
            WHERE f.original_name LIKE ? OR f.tags LIKE ? OR c.name LIKE ?
        ''', (f'%{q}%', f'%{q}%', f'%{q}%'))
    else:
        cursor.execute('''
            SELECT f.id, f.original_name, f.filename, c.name, f.visibility, f.tags
            FROM files f
            LEFT JOIN collections c ON f.collection_id = c.id
        ''')
        
    files = [{
        'id': row[0],
        'original_name': row[1],
        'filename': row[2],
        'collection_name': row[3] or 'Sin colección',
        'visibility': row[4],
        'tags': row[5]
    } for row in cursor.fetchall()]
    
    conn.close()
    
    total_size = 0
    for root, dirs, filenames in os.walk(FILES_DIR):
        for f in filenames:
            fp = os.path.join(root, f)
            total_size += os.path.getsize(fp)
    storage_mb = round(total_size / (1024 * 1024), 2)
    
    return render_template('index.html', collections=collections, files=files, q=q, storage_mb=storage_mb)

@app.route('/subir', methods=['POST'])
@login_required
def subir_archivo():
    if 'archivo' not in request.files:
        flash('No se seleccionó ningún archivo.', 'danger')
        return redirect(url_for('index'))

    file = request.files['archivo']
    if not file or not file.filename:
        flash('Selecciona un archivo válido antes de subirlo.', 'danger')
        return redirect(url_for('index'))

    safe_name = secure_filename(file.filename)
    if not safe_name:
        flash('El nombre del archivo no es válido.', 'danger')
        return redirect(url_for('index'))

    collection_id = request.form.get('collection_id') or None
    # En la base institucional collection_id es obligatorio: usar la primera colección
    # disponible si el formulario llega vacío o con un valor inválido.
    with closing(db_connect()) as check_conn:
        valid_collection = check_conn.execute('SELECT id FROM collections WHERE id = ?', (collection_id,)).fetchone() if collection_id else None
        if not valid_collection:
            fallback_collection = check_conn.execute('SELECT id FROM collections ORDER BY id LIMIT 1').fetchone()
            collection_id = fallback_collection[0] if fallback_collection else None
    if collection_id is None:
        flash('Primero debes crear una colección para guardar documentos.', 'danger')
        return redirect(url_for('index'))
    visibility = request.form.get('visibility', 'publico')
    if visibility not in ('publico', 'institucion', 'privado'):
        visibility = 'publico'
    tags = request.form.get('tags', '').strip()

    # UUID evita que dos cargas realizadas en el mismo segundo se sobrescriban.
    filename = f"{uuid4().hex}_{safe_name}"
    filepath = os.path.join(FILES_DIR, filename)

    try:
        file.save(filepath)
        with closing(db_connect()) as conn:
            with conn:
                import mimetypes
                mime = mimetypes.guess_type(safe_name)[0] or 'application/octet-stream'
                size = os.path.getsize(filepath)
                insert_compatible(conn, 'files', {
                'original_name': file.filename,
                'filename': filename,
                'stored_name': filename,
                'collection_id': collection_id,
                'visibility': visibility,
                'tags': tags,
                'created_at': datetime.now().isoformat(),
                'owner_id': 1,
                'mime': mime,
                'size': size,
                'share_token': uuid4().hex
            })
        flash('Archivo subido exitosamente.', 'success')
    except sqlite3.OperationalError:
        if os.path.exists(filepath):
            os.remove(filepath)
        app.logger.exception('No fue posible registrar el archivo en SQLite')
        flash('La base de datos está ocupada. Espera unos segundos e inténtalo de nuevo.', 'danger')
    except Exception:
        if os.path.exists(filepath):
            os.remove(filepath)
        app.logger.exception('Error al subir archivo')
        flash('No se pudo subir el archivo. Verifica el formato y vuelve a intentarlo.', 'danger')

    return redirect(url_for('index'))

@app.route('/descargar/<int:file_id>')
@login_required
def descargar_archivo(file_id):
    conn = db_connect()
    cursor = conn.cursor()
    cursor.execute("SELECT filename, original_name FROM files WHERE id = ?", (file_id,))
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return send_from_directory(FILES_DIR, row[0], download_name=row[1], as_attachment=True)
    flash('Archivo no encontrado', 'danger')
    return redirect(url_for('index'))

@app.route('/eliminar_archivo/<int:file_id>', methods=['POST'])
@login_required
def eliminar_archivo(file_id):
    conn = db_connect()
    cursor = conn.cursor()
    cursor.execute("SELECT filename FROM files WHERE id = ?", (file_id,))
    row = cursor.fetchone()
    if row:
        filepath = os.path.join(FILES_DIR, row[0])
        if os.path.exists(filepath):
            os.remove(filepath)
        cursor.execute("DELETE FROM files WHERE id = ?", (file_id,))
        conn.commit()
        flash('Archivo eliminado correctamente', 'success')
    conn.close()
    return redirect(url_for('index'))

@app.route('/crear_coleccion', methods=['POST'])
@login_required
def crear_coleccion():
    nombre = request.form.get('nombre')
    descripcion = request.form.get('descripcion', '')
    if nombre:
        conn = db_connect()
        insert_compatible(conn, 'collections', {'name': nombre, 'description': descripcion})
        conn.commit()
        conn.close()
        flash('Colección creada correctamente', 'success')
    return redirect(url_for('index'))

@app.route('/eliminar_coleccion/<int:collection_id>', methods=['POST'])
@login_required
def eliminar_coleccion(collection_id):
    conn = db_connect()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM collections WHERE id = ?", (collection_id,))
    conn.commit()
    conn.close()
    flash('Colección eliminada', 'success')
    return redirect(url_for('index'))

@app.route('/backup', methods=['POST'])
@login_required
def generar_backup():
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_filename = f"backup_rdi_{timestamp}.db"
    backup_path = os.path.join(BACKUP_DIR, backup_filename)
    try:
        with closing(db_connect()) as source, closing(sqlite3.connect(backup_path, timeout=30)) as target:
            source.backup(target)
        flash(f'Copia de seguridad creada: {backup_filename}', 'success')
    except sqlite3.Error:
        app.logger.exception('No se pudo generar el respaldo')
        flash('No fue posible generar el respaldo. Inténtalo nuevamente.', 'danger')
    return redirect(url_for('index'))

@app.errorhandler(413)
def archivo_demasiado_grande(error):
    flash('El archivo supera el límite permitido de 100 MB.', 'danger')
    return redirect(url_for('index'))

if __name__ == '__main__':
    # Sin recargador automático: evita dos procesos Flask intentando inicializar SQLite.
    app.run(debug=False, use_reloader=False, threaded=True, port=5000)
