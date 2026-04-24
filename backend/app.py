from flask import Flask, render_template, request, redirect, url_for
from flask import session
from flask import flash
from flask import jsonify
from werkzeug.security import generate_password_hash, check_password_hash
import psycopg2
import os

DATABASE_URL = os.environ.get("DATABASE_URL")

def get_db_connection():
    return psycopg2.connect(DATABASE_URL)

def crear_tablas():
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id SERIAL PRIMARY KEY,
            dni VARCHAR(15) UNIQUE NOT NULL,
            nombres VARCHAR(100) NOT NULL,
            apellidos VARCHAR(100) NOT NULL,
            telefono VARCHAR(20) NOT NULL,
            correo VARCHAR(100),
            password TEXT NOT NULL,
            rol VARCHAR(20) NOT NULL
        );
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS grados (
            id SERIAL PRIMARY KEY,
            nivel VARCHAR(20),
            nombre VARCHAR(50),
            UNIQUE (nivel, nombre)
        );
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS estudiantes (
            id SERIAL PRIMARY KEY,
            usuario_id INTEGER UNIQUE REFERENCES usuarios(id) ON DELETE CASCADE,
            grado_id INTEGER REFERENCES grados(id)
        );
    """)

    # AREAS
    cur.execute("""
        CREATE TABLE IF NOT EXISTS areas (
            id SERIAL PRIMARY KEY,
            nombre VARCHAR(100) NOT NULL
        );
    """)

    # SUBAREAS
    cur.execute("""
        CREATE TABLE IF NOT EXISTS subareas (
            id SERIAL PRIMARY KEY,
            nombre VARCHAR(100) NOT NULL,
            area_id INTEGER REFERENCES areas(id) ON DELETE CASCADE
        );
    """)

    # RELACION GRADO - SUBAREAS (IMPORTANTE)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS grado_subareas (
            id SERIAL PRIMARY KEY,
            grado_id INTEGER REFERENCES grados(id) ON DELETE CASCADE,
            subarea_id INTEGER REFERENCES subareas(id) ON DELETE CASCADE,
            UNIQUE (grado_id, subarea_id)
        );
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS docente_grado_subarea (
            id SERIAL PRIMARY KEY,
            usuario_id INTEGER REFERENCES usuarios(id) ON DELETE CASCADE,
            grado_subarea_id INTEGER REFERENCES grado_subareas(id) ON DELETE CASCADE,
            UNIQUE(usuario_id, grado_subarea_id)
        );
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS notas_bimestrales (
            id SERIAL PRIMARY KEY,
            estudiante_id INTEGER REFERENCES estudiantes(id) ON DELETE CASCADE,
            grado_id INTEGER REFERENCES grados(id) ON DELETE CASCADE,
            subarea_id INTEGER REFERENCES subareas(id) ON DELETE CASCADE,

            b1 INTEGER CHECK (b1 BETWEEN 0 AND 20),
            b2 INTEGER CHECK (b2 BETWEEN 0 AND 20),
            b3 INTEGER CHECK (b3 BETWEEN 0 AND 20),
            b4 INTEGER CHECK (b4 BETWEEN 0 AND 20),

            UNIQUE(estudiante_id, grado_id, subarea_id)
        );
    """)

    

    conn.commit()
    cur.close()
    conn.close()

def crear_admin():
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO usuarios (dni, nombres, apellidos, telefono, correo, password, rol)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (dni) DO NOTHING;
    """, (
        "74043318",
        "Admin",
        "Principal",
        "999999999",
        "admin@siga.com",
        generate_password_hash("123"),
        "admin"
    ))

    conn.commit()
    cur.close()
    conn.close()

def insertar_datos_base():
    conn = get_db_connection()
    cur = conn.cursor()

    # grados
    # cur.execute("""
    #     INSERT INTO grados (nivel, nombre) VALUES
    #     ('Primaria','1ro'), ('Primaria','2do'), ('Primaria','3ro'),
    #     ('Primaria','4to'), ('Primaria','Sigma'), ('Primaria','Omega'),
    #     ('Secundaria','Basico'), ('Secundaria','Intermedio'),
    #     ('Secundaria','Avanzado'), ('Secundaria','Primera Seleccion')
    #     ON CONFLICT DO NOTHING;
    # """)

    conn.commit()
    cur.close()
    conn.close()

def borrar_tabla():
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("DROP TABLE IF EXISTS notas_bimestrales;")

    conn.commit()
    cur.close()
    conn.close()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(
    __name__,
    template_folder=os.path.join(BASE_DIR, "../frontend/templates"),
    static_folder=os.path.join(BASE_DIR, "../frontend/static")
)

app.secret_key = os.environ.get("SECRET_KEY", "dev_key")

# Landing
@app.route("/")
def index():
    return render_template("index.html")

# Login
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        print("FORM DATA:", request.form)

        dni = request.form.get("dni")
        password = request.form.get("password")

        if not dni or not password:
            return "Faltan datos"

        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute(
            "SELECT id, dni, password, rol FROM usuarios WHERE dni = %s",
            (dni,)
        )

        user = cur.fetchone()

        if user and check_password_hash(user[2], password):

            session["user_id"] = user[0]
            session["rol"] = user[3]

            if user[3] == "estudiante":
                return redirect(url_for("dashboard_estudiante"))
            elif user[3] == "docente":
                return redirect(url_for("dashboard_docente"))
            elif user[3] == "admin":
                return redirect(url_for("dashboard_admin"))

        return "Credenciales incorrectas"

    return render_template("login.html")

# Dashboard
@app.route("/dashboard/estudiante")
def dashboard_estudiante():
    if session.get("rol") != "estudiante":
        return redirect(url_for("login"))

    user_id = session.get("user_id")

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT 
            s.nombre,
            COALESCE(n.b1, 0),
            COALESCE(n.b2, 0),
            COALESCE(n.b3, 0),
            COALESCE(n.b4, 0)
        FROM estudiantes e
        JOIN grado_subareas gs ON e.grado_id = gs.grado_id
        JOIN subareas s ON gs.subarea_id = s.id

        LEFT JOIN notas_bimestrales n
            ON n.estudiante_id = e.id
            AND n.subarea_id = s.id
            AND n.grado_id = e.grado_id

        WHERE e.usuario_id = %s
        ORDER BY s.nombre;
    """, (user_id,))

    cursos = cur.fetchall()

    cur.execute("""
        SELECT g.nombre
        FROM estudiantes e
        JOIN grados g ON e.grado_id = g.id
        WHERE e.usuario_id = %s
    """, (user_id,))

    grado = cur.fetchone()

    cur.close()
    conn.close()

    return render_template(
            "dashboard_estudiante.html",
            cursos=cursos,
            grado=grado
        )

@app.route("/dashboard/docente")
def dashboard_docente():
    if session.get("rol") != "docente":
        return redirect(url_for("login"))

    user_id = session.get("user_id")

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT dgs.id, g.nombre, s.nombre, g.id, s.id
        FROM docente_grado_subarea dgs
        JOIN grado_subareas gs ON dgs.grado_subarea_id = gs.id
        JOIN grados g ON gs.grado_id = g.id
        JOIN subareas s ON gs.subarea_id = s.id
        WHERE dgs.usuario_id = %s
    """, (user_id,))

    cursos = cur.fetchall()

    cur.close()
    conn.close()

    return render_template("dashboard_docente.html", cursos=cursos)

@app.route("/docente/curso/<int:grado_id>/<int:subarea_id>")
def ver_estudiantes(grado_id, subarea_id):

    if session.get("rol") != "docente":
        return redirect(url_for("login"))

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT 
            e.id,
            u.nombres,
            u.apellidos,
            u.dni,
            COALESCE(n.b1, 0),
            COALESCE(n.b2, 0),
            COALESCE(n.b3, 0),
            COALESCE(n.b4, 0)
        FROM estudiantes e
        JOIN usuarios u ON e.usuario_id = u.id
        LEFT JOIN notas_bimestrales n 
            ON n.estudiante_id = e.id 
            AND n.grado_id = %s
            AND n.subarea_id = %s
        WHERE e.grado_id = %s
    """, (grado_id, subarea_id, grado_id))

    estudiantes = cur.fetchall()

    cur.close()
    conn.close()

    return jsonify({"estudiantes": estudiantes})

@app.route("/docente/guardar_notas", methods=["POST"])
def guardar_notas():

    data = request.json

    estudiante_id = data["estudiante_id"]
    grado_id = data["grado_id"]

    b1 = int(data["b1"])
    b2 = int(data["b2"])
    b3 = int(data["b3"])
    b4 = int(data["b4"])

    # validación rápida
    for n in [b1, b2, b3, b4]:
        if n < 0 or n > 20:
            return {"error": "Notas inválidas"}, 400

    conn = get_db_connection()
    cur = conn.cursor()

    subarea_id = data["subarea_id"]

    cur.execute("""
        INSERT INTO notas_bimestrales 
        (estudiante_id, grado_id, subarea_id, b1, b2, b3, b4)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (estudiante_id, grado_id, subarea_id)
        DO UPDATE SET 
            b1 = EXCLUDED.b1,
            b2 = EXCLUDED.b2,
            b3 = EXCLUDED.b3,
            b4 = EXCLUDED.b4;
    """, (estudiante_id, grado_id, subarea_id, b1, b2, b3, b4))

    conn.commit()
    cur.close()
    conn.close()

    return jsonify({
        "ok": True,
        "message": "Notas guardadas exitosamente"
    })


@app.route("/dashboard/admin")
def dashboard_admin():
    if session.get("rol") != "admin":
        return redirect(url_for("login"))

    conn = get_db_connection()
    cur = conn.cursor()

    # usuarios
    cur.execute("""
        SELECT u.id, u.dni, u.nombres, u.apellidos, u.rol,
            g.nombre
        FROM usuarios u
        LEFT JOIN estudiantes e ON u.id = e.usuario_id
        LEFT JOIN grados g ON e.grado_id = g.id
    """)
    usuarios = cur.fetchall()

    # grados
    cur.execute("SELECT * FROM grados")
    grados = cur.fetchall()

    cur.execute("SELECT * FROM areas")
    areas = cur.fetchall()

    cur.execute("SELECT * FROM subareas")
    subareas = cur.fetchall()

    # ESTRUCTURA AREAS - SUBAREAS
    cur.execute("""
        SELECT a.nombre, s.nombre
        FROM areas a
        LEFT JOIN subareas s ON a.id = s.area_id
        ORDER BY a.id;
    """)
    estructura_areas = cur.fetchall()

    # ESTRUCTURA GRADOS - SUBAREAS
    cur.execute("""
        SELECT g.nombre, a.nombre, s.nombre
        FROM grado_subareas gs
        JOIN grados g ON gs.grado_id = g.id
        JOIN subareas s ON gs.subarea_id = s.id
        JOIN areas a ON s.area_id = a.id
        ORDER BY g.id;
    """)
    estructura_grados = cur.fetchall()

    cur.execute("""
        SELECT gs.id, g.nombre, s.nombre
        FROM grado_subareas gs
        JOIN grados g ON gs.grado_id = g.id
        JOIN subareas s ON gs.subarea_id = s.id
    """)
    grado_subareas = cur.fetchall()

    cur.close()
    conn.close()

    return render_template(
        "dashboard_admin.html",
        usuarios=usuarios,
        grados=grados,
        areas=areas,
        subareas=subareas,
        estructura_areas=estructura_areas,
        estructura_grados=estructura_grados,
        grado_subareas=grado_subareas
    )

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))

@app.route("/crear_usuario", methods=["POST"])
def crear_usuario():
    if session.get("rol") != "admin":
        return redirect(url_for("login"))

    # obtener datos
    dni = request.form.get("dni")
    nombres = request.form.get("nombres")
    apellidos = request.form.get("apellidos")
    telefono = request.form.get("telefono")
    correo = request.form.get("correo")
    password = request.form.get("password")
    rol = request.form.get("rol")
    grado_id = request.form.get("grado_id")

    # validaciones
    if not all([dni, nombres, apellidos, telefono, password, rol]):
        return "Faltan campos obligatorios"

    if rol == "estudiante" and (not grado_id):
        return "Falta grado"

    # recién aquí hasheas
    password_hash = generate_password_hash(password)

    conn = get_db_connection()
    cur = conn.cursor()

    try:
        cur.execute("""
            INSERT INTO usuarios (dni, nombres, apellidos, telefono, correo, password, rol)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id;
        """, (dni, nombres, apellidos, telefono, correo, password_hash, rol))

        usuario_id = cur.fetchone()[0]

        if rol == "estudiante":
            cur.execute("""
                INSERT INTO estudiantes (usuario_id, grado_id)
                VALUES (%s, %s)
            """, (usuario_id, int(grado_id)))

        conn.commit()

    except psycopg2.errors.UniqueViolation:
        conn.rollback()
        return "El DNI ya existe"

    finally:
        cur.close()
        conn.close()

    return redirect(url_for("dashboard_admin"))

@app.route("/eliminar_usuario/<dni>")
def eliminar_usuario(dni):
    if session.get("rol") != "admin":
        return redirect(url_for("login"))

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("DELETE FROM usuarios WHERE dni = %s", (dni,))

    conn.commit()
    cur.close()
    conn.close()

    return redirect(url_for("dashboard_admin"))

@app.route("/cambiar_password", methods=["POST"])
def cambiar_password():
    if session.get("rol") != "admin":
        return redirect(url_for("login"))

    dni = request.form["dni"]
    nueva_password = generate_password_hash(request.form["password"])

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        UPDATE usuarios
        SET password = %s
        WHERE dni = %s
    """, (nueva_password, dni))

    conn.commit()
    cur.close()
    conn.close()

    flash("Contraseña actualizada correctamente", "success")
    return redirect(url_for("dashboard_admin"))

@app.route("/ver_usuarios")
def ver_usuarios():
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("SELECT * FROM usuarios;")
    datos = cur.fetchall()

    cur.close()
    conn.close()

    return str(datos)

@app.route("/ver_grados")
def ver_grados():
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("SELECT id, nivel, nombre FROM grados ORDER BY id;")
    grados = cur.fetchall()

    cur.close()
    conn.close()

    resultado = "<h2>Grados</h2><ul>"
    for g in grados:
        resultado += f"<li>ID: {g[0]} | {g[1]} - {g[2]}</li>"
    resultado += "</ul>"

    return resultado

@app.route("/cambiar_grado", methods=["POST"])
def cambiar_grado():
    if session.get("rol") != "admin":
        return redirect(url_for("login"))

    dni = request.form["dni"]
    grado_id = request.form["grado_id"]

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        UPDATE estudiantes
        SET grado_id = %s
        WHERE usuario_id = (
            SELECT id FROM usuarios WHERE dni = %s
        )
        RETURNING *;
    """, (grado_id, dni))

    conn.commit()
    cur.close()
    conn.close()

    flash("Grado actualizado correctamente", "success")
    return redirect(url_for("dashboard_admin"))

@app.route("/estructura/vista")
def vista_estructura():
    conn = get_db_connection()
    cur = conn.cursor()

    # ÁREAS → SUBÁREAS
    cur.execute("""
        SELECT a.nombre, s.nombre
        FROM areas a
        LEFT JOIN subareas s ON a.id = s.area_id
        ORDER BY a.id;
    """)
    areas = cur.fetchall()

    # GRADOS → SUBÁREAS
    cur.execute("""
        SELECT g.nombre, s.nombre
        FROM grado_subareas gs
        JOIN grados g ON gs.grado_id = g.id
        JOIN subareas s ON gs.subarea_id = s.id
        ORDER BY g.id;
    """)
    grados = cur.fetchall()

    cur.close()
    conn.close()

    return render_template("estructura.html", areas=areas, grados=grados)

@app.route("/admin/area/crear", methods=["POST"])
def crear_area():
    nombre = request.form["nombre"]

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO areas (nombre)
        VALUES (%s)
        ON CONFLICT DO NOTHING;
    """, (nombre,))

    conn.commit()
    cur.close()
    conn.close()

    flash("Área creada correctamente", "success")
    return redirect(url_for("dashboard_admin"))

@app.route("/admin/subarea/crear", methods=["POST"])
def crear_subarea():
    nombre = request.form["nombre"]
    area_id = request.form["area_id"]

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO subareas (nombre, area_id)
        VALUES (%s, %s)
    """, (nombre, area_id))

    conn.commit()
    cur.close()
    conn.close()

    flash("Subarea creada correctamente", "success")
    return redirect(url_for("dashboard_admin"))

@app.route("/admin/grado-subarea/crear", methods=["POST"])
def asignar_subarea():
    grado_id = request.form["grado_id"]
    subarea_id = request.form["subarea_id"]

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO grado_subareas (grado_id, subarea_id)
        VALUES (%s, %s)
        ON CONFLICT DO NOTHING;
    """, (grado_id, subarea_id))

    conn.commit()
    cur.close()
    conn.close()

    flash("Relación creada correctamente", "success")
    return redirect(url_for("dashboard_admin"))

@app.route("/admin/area/eliminar/<int:area_id>", methods=["POST"])
def eliminar_area(area_id):
    if session.get("rol") != "admin":
        return redirect(url_for("login"))

    conn = get_db_connection()
    cur = conn.cursor()

    # elimina el área (y por CASCADE se borran subáreas si está bien tu FK)
    cur.execute("DELETE FROM areas WHERE id = %s", (area_id,))

    conn.commit()
    cur.close()
    conn.close()

    flash("Área eliminada correctamente", "success")
    return redirect(url_for("dashboard_admin"))

@app.route("/admin/docente-curso/asignar", methods=["POST"])
def asignar_docente_curso():

    usuario_id = request.form["usuario_id"]
    grado_subarea_id = request.form["grado_subarea_id"]

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO docente_grado_subarea (usuario_id, grado_subarea_id)
        VALUES (%s, %s)
        ON CONFLICT DO NOTHING;
    """, (usuario_id, grado_subarea_id))

    conn.commit()
    cur.close()
    conn.close()

    flash("Docente asignado correctamente")
    return redirect(url_for("dashboard_admin"))

if __name__ == "__main__":
    crear_tablas()
    crear_admin()
    app.run()