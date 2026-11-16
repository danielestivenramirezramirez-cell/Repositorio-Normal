# Repositorio Digital Institucional — ENSCM

## Cambios incluidos
- Escudo institucional y mascota normalista en la navegación, el acceso y el encabezado principal.
- Conexiones SQLite con espera de hasta 30 segundos, `busy_timeout` y modo WAL para reducir bloqueos entre operaciones.
- Compatibilidad de inserción con la estructura de base de datos incluida en el proyecto (incluye campos `owner_id`, `stored_name`, `mime`, `size` y `share_token` cuando existen).
- Cargas con nombres internos únicos, validación del nombre y límite de 100 MB.
- Copias de seguridad mediante la API de respaldo de SQLite.

## Ejecución local en Windows
1. Instala Python 3.10 o superior.
2. Abre una terminal en la carpeta `repositorio alejandra`.
3. Crea un entorno e instala dependencias:

   ```powershell
   py -m venv venv
   .\venv\Scripts\activate
   pip install -r requirements.txt
   ```

4. Inicia el sistema:

   ```powershell
   python main.py
   ```

5. Abre `http://127.0.0.1:5000` en el navegador.

## Importante para el despliegue
- Mantén una sola instancia de la aplicación escribiendo en el mismo archivo SQLite. WAL mejora la concurrencia, pero SQLite no debe compartirse como base de datos de escritura entre varias máquinas/instancias.
- El directorio `datos/` debe tener permisos de lectura y escritura y estar en almacenamiento persistente.
- Configura la variable de entorno `SECRET_KEY` con una clave privada antes de publicar el sistema.
- El límite máximo de carga está configurado en 100 MB.
