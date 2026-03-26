from flask import Flask, render_template, request, redirect, url_for

app = Flask(__name__,
            template_folder="../frontend/templates",
            static_folder="../frontend/static")

# Usuarios simulados
usuarios = [
    {"username": "alumno", "password": "123", "rol": "estudiante"},
    {"username": "profe", "password": "123", "rol": "docente"}
]

# Landing
@app.route("/")
def index():
    return render_template("index.html")

# Login GET
@app.route("/login")
def login():
    return render_template("login.html")

# Login POST (validación)
@app.route("/login", methods=["POST"])
def login_post():
    username = request.form["username"]
    password = request.form["password"]

    for user in usuarios:
        if user["username"] == username and user["password"] == password:
            return redirect(url_for("dashboard", rol=user["rol"]))

    return "Credenciales incorrectas"

# Dashboard
@app.route("/dashboard")
def dashboard():
    rol = request.args.get("rol")
    return render_template("dashboard.html", rol=rol)

if __name__ == "__main__":
    app.run(debug=True)