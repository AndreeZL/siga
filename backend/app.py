from functools import wraps
from dotenv import load_dotenv
import os

import psycopg2
from flask import Flask, flash, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))


app = Flask(
    __name__,
    template_folder=os.path.join(BASE_DIR, "../frontend/templates"),
    static_folder=os.path.join(BASE_DIR, "../frontend/static"),
)
app.secret_key = os.environ.get("SECRET_KEY", "dev_key")


def get_db_connection():
    if not DATABASE_URL:
        raise RuntimeError("Configura la variable de entorno DATABASE_URL.")
    return psycopg2.connect(DATABASE_URL)


def execute(query, params=None, fetchone=False, fetchall=False):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params or ())
            if fetchone:
                return cur.fetchone()
            if fetchall:
                return cur.fetchall()
    return None


def role_required(role):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if session.get("rol") != role:
                flash("Inicia sesión para continuar.", "error")
                return redirect(url_for("login"))
            return view(*args, **kwargs)

        return wrapped

    return decorator


def crear_tablas():
    statements = [
        """
        CREATE TABLE IF NOT EXISTS usuarios (
            id SERIAL PRIMARY KEY,
            dni VARCHAR(15) UNIQUE NOT NULL,
            nombres VARCHAR(100) NOT NULL,
            apellidos VARCHAR(100) NOT NULL,
            telefono VARCHAR(20) NOT NULL,
            correo VARCHAR(100),
            password TEXT NOT NULL,
            rol VARCHAR(20) NOT NULL CHECK (rol IN ('admin', 'docente', 'estudiante'))
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS grados (
            id SERIAL PRIMARY KEY,
            nivel VARCHAR(20) NOT NULL,
            nombre VARCHAR(50) NOT NULL,
            UNIQUE (nivel, nombre)
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS estudiantes (
            id SERIAL PRIMARY KEY,
            usuario_id INTEGER UNIQUE REFERENCES usuarios(id) ON DELETE CASCADE,
            grado_id INTEGER REFERENCES grados(id)
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS areas (
            id SERIAL PRIMARY KEY,
            nombre VARCHAR(100) NOT NULL
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS subareas (
            id SERIAL PRIMARY KEY,
            nombre VARCHAR(100) NOT NULL,
            area_id INTEGER REFERENCES areas(id) ON DELETE CASCADE
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS grado_subareas (
            id SERIAL PRIMARY KEY,
            grado_id INTEGER REFERENCES grados(id) ON DELETE CASCADE,
            subarea_id INTEGER REFERENCES subareas(id) ON DELETE CASCADE,
            UNIQUE (grado_id, subarea_id)
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS docente_grado_subarea (
            id SERIAL PRIMARY KEY,
            usuario_id INTEGER REFERENCES usuarios(id) ON DELETE CASCADE,
            grado_subarea_id INTEGER REFERENCES grado_subareas(id) ON DELETE CASCADE,
            UNIQUE(usuario_id, grado_subarea_id)
        );
        """,
        """
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
        """,
    ]

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            for statement in statements:
                cur.execute(statement)


def crear_admin():
    admin_dni = os.environ.get("ADMIN_DNI", "74043318")
    admin_password = os.environ.get("ADMIN_PASSWORD", "123")

    execute(
        """
        INSERT INTO usuarios (dni, nombres, apellidos, telefono, correo, password, rol)
        VALUES (%s, %s, %s, %s, %s, %s, 'admin')
        ON CONFLICT (dni) DO NOTHING;
        """,
        (
            admin_dni,
            os.environ.get("ADMIN_NOMBRES", "Admin"),
            os.environ.get("ADMIN_APELLIDOS", "Principal"),
            os.environ.get("ADMIN_TELEFONO", "999999999"),
            os.environ.get("ADMIN_CORREO", "admin@siga.com"),
            generate_password_hash(admin_password),
        ),
    )


def inicializar_bd():
    crear_tablas()
    crear_admin()


def docente_tiene_curso(usuario_id, grado_id, subarea_id):
    row = execute(
        """
        SELECT 1
        FROM docente_grado_subarea dgs
        JOIN grado_subareas gs ON dgs.grado_subarea_id = gs.id
        WHERE dgs.usuario_id = %s
          AND gs.grado_id = %s
          AND gs.subarea_id = %s;
        """,
        (usuario_id, grado_id, subarea_id),
        fetchone=True,
    )
    return row is not None


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        dni = request.form.get("dni", "").strip()
        password = request.form.get("password", "")

        if not dni or not password:
            flash("Ingresa tu usuario y contraseña.", "error")
            return redirect(url_for("login"))

        user = execute(
            "SELECT id, password, rol FROM usuarios WHERE dni = %s;",
            (dni,),
            fetchone=True,
        )

        if user and check_password_hash(user[1], password):
            session.clear()
            session["user_id"] = user[0]
            session["rol"] = user[2]

            dashboards = {
                "estudiante": "dashboard_estudiante",
                "docente": "dashboard_docente",
                "admin": "dashboard_admin",
            }
            return redirect(url_for(dashboards[user[2]]))

        flash("Credenciales incorrectas.", "error")
        return redirect(url_for("login"))

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("Sesión cerrada correctamente.", "success")
    return redirect(url_for("index"))


@app.route("/dashboard/estudiante")
@role_required("estudiante")
def dashboard_estudiante():
    user_id = session["user_id"]

    cursos = execute(
        """
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
        """,
        (user_id,),
        fetchall=True,
    )

    grado = execute(
        """
        SELECT g.nombre, g.nivel
        FROM estudiantes e
        JOIN grados g ON e.grado_id = g.id
        WHERE e.usuario_id = %s;
        """,
        (user_id,),
        fetchone=True,
    )

    return render_template("dashboard_estudiante.html", cursos=cursos, grado=grado)


@app.route("/dashboard/docente")
@role_required("docente")
def dashboard_docente():
    cursos_rows = execute(
        """
        SELECT dgs.id, g.nombre, s.nombre, g.id, s.id, g.nivel
        FROM docente_grado_subarea dgs
        JOIN grado_subareas gs ON dgs.grado_subarea_id = gs.id
        JOIN grados g ON gs.grado_id = g.id
        JOIN subareas s ON gs.subarea_id = s.id
        WHERE dgs.usuario_id = %s
        ORDER BY g.nivel, g.nombre, s.nombre;
        """,
        (session["user_id"],),
        fetchall=True,
    )
    cursos = [
        {
            "asignacion_id": row[0],
            "grado": row[1],
            "subarea": row[2],
            "grado_id": row[3],
            "subarea_id": row[4],
            "nivel": row[5],
        }
        for row in cursos_rows
    ]
    return render_template("dashboard_docente.html", cursos=cursos)


@app.route("/docente/curso/<int:grado_id>/<int:subarea_id>")
@role_required("docente")
def ver_estudiantes(grado_id, subarea_id):
    if not docente_tiene_curso(session["user_id"], grado_id, subarea_id):
        return jsonify({"error": "No tienes permiso para este curso."}), 403

    estudiantes = execute(
        """
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
        ORDER BY u.apellidos, u.nombres;
        """,
        (grado_id, subarea_id, grado_id),
        fetchall=True,
    )
    return jsonify({"estudiantes": estudiantes})


@app.route("/docente/guardar_notas", methods=["POST"])
@role_required("docente")
def guardar_notas():
    data = request.get_json(silent=True) or {}
    required = ["estudiante_id", "grado_id", "subarea_id", "b1", "b2", "b3", "b4"]

    if not all(key in data for key in required):
        return jsonify({"error": "Faltan datos para guardar las notas."}), 400

    try:
        estudiante_id = int(data["estudiante_id"])
        grado_id = int(data["grado_id"])
        subarea_id = int(data["subarea_id"])
        notas = [int(data[key]) for key in ["b1", "b2", "b3", "b4"]]
    except (TypeError, ValueError):
        return jsonify({"error": "Las notas deben ser números enteros."}), 400

    if any(nota < 0 or nota > 20 for nota in notas):
        return jsonify({"error": "Las notas deben estar entre 0 y 20."}), 400

    if not docente_tiene_curso(session["user_id"], grado_id, subarea_id):
        return jsonify({"error": "No tienes permiso para guardar notas en este curso."}), 403

    estudiante = execute(
        "SELECT 1 FROM estudiantes WHERE id = %s AND grado_id = %s;",
        (estudiante_id, grado_id),
        fetchone=True,
    )
    if not estudiante:
        return jsonify({"error": "El estudiante no pertenece al grado seleccionado."}), 400

    execute(
        """
        INSERT INTO notas_bimestrales
            (estudiante_id, grado_id, subarea_id, b1, b2, b3, b4)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (estudiante_id, grado_id, subarea_id)
        DO UPDATE SET
            b1 = EXCLUDED.b1,
            b2 = EXCLUDED.b2,
            b3 = EXCLUDED.b3,
            b4 = EXCLUDED.b4;
        """,
        (estudiante_id, grado_id, subarea_id, *notas),
    )

    return jsonify({"ok": True, "message": "Notas guardadas correctamente."})


@app.route("/dashboard/admin")
@role_required("admin")
def dashboard_admin():
    usuarios = execute(
        """
        SELECT
            u.id,
            u.dni,
            u.nombres,
            u.apellidos,
            u.rol,
            e.grado_id,
            g.nombre,
            g.nivel
        FROM usuarios u
        LEFT JOIN estudiantes e ON u.id = e.usuario_id
        LEFT JOIN grados g ON e.grado_id = g.id
        ORDER BY u.rol, u.apellidos, u.nombres;
        """,
        fetchall=True,
    )
    grados = execute("SELECT id, nivel, nombre FROM grados ORDER BY nivel, nombre;", fetchall=True)
    areas = execute("SELECT id, nombre FROM areas ORDER BY nombre;", fetchall=True)
    subareas = execute(
        """
        SELECT s.id, s.nombre, a.nombre
        FROM subareas s
        JOIN areas a ON s.area_id = a.id
        ORDER BY a.nombre, s.nombre;
        """,
        fetchall=True,
    )
    estructura_areas = execute(
        """
        SELECT a.nombre, s.nombre
        FROM areas a
        LEFT JOIN subareas s ON a.id = s.area_id
        ORDER BY a.nombre, s.nombre;
        """,
        fetchall=True,
    )
    estructura_grados = execute(
        """
        SELECT g.nombre, a.nombre, s.nombre
        FROM grado_subareas gs
        JOIN grados g ON gs.grado_id = g.id
        JOIN subareas s ON gs.subarea_id = s.id
        JOIN areas a ON s.area_id = a.id
        ORDER BY g.nivel, g.nombre, a.nombre, s.nombre;
        """,
        fetchall=True,
    )
    grado_subareas = execute(
        """
        SELECT gs.id, g.nombre, s.nombre, g.nivel
        FROM grado_subareas gs
        JOIN grados g ON gs.grado_id = g.id
        JOIN subareas s ON gs.subarea_id = s.id
        ORDER BY g.nivel, g.nombre, s.nombre;
        """,
        fetchall=True,
    )

    return render_template(
        "dashboard_admin.html",
        usuarios=usuarios,
        grados=grados,
        areas=areas,
        subareas=subareas,
        estructura_areas=estructura_areas,
        estructura_grados=estructura_grados,
        grado_subareas=grado_subareas,
    )


@app.route("/crear_usuario", methods=["POST"])
@role_required("admin")
def crear_usuario():
    dni = request.form.get("dni", "").strip()
    nombres = request.form.get("nombres", "").strip()
    apellidos = request.form.get("apellidos", "").strip()
    telefono = request.form.get("telefono", "").strip()
    correo = request.form.get("correo", "").strip() or None
    password = request.form.get("password", "")
    rol = request.form.get("rol", "")
    grado_id = request.form.get("grado_id")

    if rol not in {"docente", "estudiante"}:
        flash("Selecciona un rol válido.", "error")
        return redirect(url_for("dashboard_admin"))

    if not all([dni, nombres, apellidos, telefono, password]):
        flash("Completa los campos obligatorios.", "error")
        return redirect(url_for("dashboard_admin"))

    if rol == "estudiante" and not grado_id:
        flash("Selecciona el grado del estudiante.", "error")
        return redirect(url_for("dashboard_admin"))

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO usuarios (dni, nombres, apellidos, telefono, correo, password, rol)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    RETURNING id;
                    """,
                    (dni, nombres, apellidos, telefono, correo, generate_password_hash(password), rol),
                )
                usuario_id = cur.fetchone()[0]

                if rol == "estudiante":
                    cur.execute(
                        "INSERT INTO estudiantes (usuario_id, grado_id) VALUES (%s, %s);",
                        (usuario_id, int(grado_id)),
                    )
    except psycopg2.errors.UniqueViolation:
        flash("El DNI ya existe.", "error")
    except psycopg2.Error:
        flash("No se pudo crear el usuario. Revisa los datos ingresados.", "error")
    else:
        flash("Usuario creado correctamente.", "success")

    return redirect(url_for("dashboard_admin"))


@app.route("/admin/usuario/<int:usuario_id>/eliminar", methods=["POST"])
@role_required("admin")
def eliminar_usuario(usuario_id):
    if usuario_id == session["user_id"]:
        flash("No puedes eliminar tu propio usuario mientras estás conectado.", "error")
        return redirect(url_for("dashboard_admin"))

    execute("DELETE FROM usuarios WHERE id = %s;", (usuario_id,))
    flash("Usuario eliminado correctamente.", "success")
    return redirect(url_for("dashboard_admin"))


@app.route("/cambiar_password", methods=["POST"])
@role_required("admin")
def cambiar_password():
    usuario_id = request.form.get("usuario_id")
    password = request.form.get("password", "")

    if not usuario_id or not password:
        flash("Ingresa una nueva contraseña.", "error")
        return redirect(url_for("dashboard_admin"))

    execute(
        "UPDATE usuarios SET password = %s WHERE id = %s;",
        (generate_password_hash(password), usuario_id),
    )
    flash("Contraseña actualizada correctamente.", "success")
    return redirect(url_for("dashboard_admin"))


@app.route("/cambiar_grado", methods=["POST"])
@role_required("admin")
def cambiar_grado():
    usuario_id = request.form.get("usuario_id")
    grado_id = request.form.get("grado_id")

    if not usuario_id or not grado_id:
        flash("Selecciona un grado válido.", "error")
        return redirect(url_for("dashboard_admin"))

    execute(
        """
        UPDATE estudiantes
        SET grado_id = %s
        WHERE usuario_id = %s;
        """,
        (grado_id, usuario_id),
    )
    flash("Grado actualizado correctamente.", "success")
    return redirect(url_for("dashboard_admin"))


@app.route("/admin/area/crear", methods=["POST"])
@role_required("admin")
def crear_area():
    nombre = request.form.get("nombre", "").strip()
    if not nombre:
        flash("Ingresa el nombre del área.", "error")
        return redirect(url_for("dashboard_admin"))

    execute("INSERT INTO areas (nombre) VALUES (%s);", (nombre,))
    flash("Área creada correctamente.", "success")
    return redirect(url_for("dashboard_admin"))


@app.route("/admin/subarea/crear", methods=["POST"])
@role_required("admin")
def crear_subarea():
    nombre = request.form.get("nombre", "").strip()
    area_id = request.form.get("area_id")

    if not nombre or not area_id:
        flash("Completa los datos de la subárea.", "error")
        return redirect(url_for("dashboard_admin"))

    execute("INSERT INTO subareas (nombre, area_id) VALUES (%s, %s);", (nombre, area_id))
    flash("Subárea creada correctamente.", "success")
    return redirect(url_for("dashboard_admin"))


@app.route("/admin/grado-subarea/crear", methods=["POST"])
@role_required("admin")
def asignar_subarea():
    grado_id = request.form.get("grado_id")
    subarea_id = request.form.get("subarea_id")

    if not grado_id or not subarea_id:
        flash("Selecciona grado y subárea.", "error")
        return redirect(url_for("dashboard_admin"))

    execute(
        """
        INSERT INTO grado_subareas (grado_id, subarea_id)
        VALUES (%s, %s)
        ON CONFLICT DO NOTHING;
        """,
        (grado_id, subarea_id),
    )
    flash("Relación creada correctamente.", "success")
    return redirect(url_for("dashboard_admin"))


@app.route("/admin/area/<int:area_id>/eliminar", methods=["POST"])
@role_required("admin")
def eliminar_area(area_id):
    execute("DELETE FROM areas WHERE id = %s;", (area_id,))
    flash("Área eliminada correctamente.", "success")
    return redirect(url_for("dashboard_admin"))


@app.route("/admin/docente-curso/asignar", methods=["POST"])
@role_required("admin")
def asignar_docente_curso():
    usuario_id = request.form.get("usuario_id")
    grado_subarea_id = request.form.get("grado_subarea_id")

    if not usuario_id or not grado_subarea_id:
        flash("Selecciona docente y curso.", "error")
        return redirect(url_for("dashboard_admin"))

    docente = execute(
        "SELECT 1 FROM usuarios WHERE id = %s AND rol = 'docente';",
        (usuario_id,),
        fetchone=True,
    )
    if not docente:
        flash("El usuario seleccionado no es docente.", "error")
        return redirect(url_for("dashboard_admin"))

    execute(
        """
        INSERT INTO docente_grado_subarea (usuario_id, grado_subarea_id)
        VALUES (%s, %s)
        ON CONFLICT DO NOTHING;
        """,
        (usuario_id, grado_subarea_id),
    )
    flash("Docente asignado correctamente.", "success")
    return redirect(url_for("dashboard_admin"))


@app.route("/estructura/vista")
@role_required("admin")
def vista_estructura():
    areas = execute(
        """
        SELECT a.nombre, s.nombre
        FROM areas a
        LEFT JOIN subareas s ON a.id = s.area_id
        ORDER BY a.nombre, s.nombre;
        """,
        fetchall=True,
    )
    grados = execute(
        """
        SELECT g.nombre, s.nombre
        FROM grado_subareas gs
        JOIN grados g ON gs.grado_id = g.id
        JOIN subareas s ON gs.subarea_id = s.id
        ORDER BY g.nombre, s.nombre;
        """,
        fetchall=True,
    )
    return render_template("estructura.html", areas=areas, grados=grados)


if DATABASE_URL and os.environ.get("AUTO_INIT_DB", "true").lower() == "true":
    inicializar_bd()


if __name__ == "__main__":
    if not DATABASE_URL:
        raise RuntimeError("Configura DATABASE_URL antes de ejecutar la aplicación.")
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1")
