import os
import sqlite3
import smtplib
import settings
from flask import Flask, flash, jsonify, url_for, redirect, render_template,request, session, send_from_directory
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename
from xtras import login_required
import datetime
from itsdangerous import URLSafeTimedSerializer
from apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__)
app.secret_key = os.urandom(24)

app.config["email"] = os.environ.get("EMAIL")
app.config["email_password"] = os.environ.get("EMAIL_PASS")

def reminder():
    conn = sqlite3.connect('data.db')
    c = conn.cursor()
    now = datetime.date.today()
    task_date = now + datetime.timedelta(days=3)
    rows = c.execute("SELECT COUNT(*) FROM tasks WHERE deadline == :d",
            {"d": task_date})
    number = c.fetchone()
    if int(number[0]) != 0:
        rows = c.execute("SELECT * FROM tasks WHERE deadline == :d",
                {"d": task_date})
        tasks = c.fetchall()
        msg = []
        for t in tasks:
            msg.append(t[1])
        SUBJECT = "Reminder: you have deadlines coming up"
        TEXT = "Deadlines of these tasks are in 3 days: " + ', '.join(msg)
        rows = c.execute("SELECT * FROM users")
        users = c.fetchall()
        server = smtplib.SMTP("smtp.gmail.com", 587)
        message = 'Subject: {}\n\n{}'.format(SUBJECT, TEXT)
        server.starttls()
        server.login(app.config['email'], app.config['email_password'])
        for u in users:
            server.sendmail("lkvatasks@gmail.com", u[1], message)
    return

sched = BackgroundScheduler(daemon=True)
sched.add_job(reminder,'interval',hours=24)
sched.start()

UPLOAD_FOLDER = './uploads'
ALLOWED_EXTENSIONS = {'txt', 'pdf', 'doc', 'docx', 'xlsx'}

app.config["TEMPLATES_AUTO_RELOAD"] = True
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response

app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"

@app.route("/")
@login_required
def index():
    conn = sqlite3.connect('data.db')
    c = conn.cursor()
    now = datetime.date.today()
    rows = c.execute("SELECT * FROM tasks WHERE deadline >= :d ORDER BY deadline ASC LIMIT 7",
            {"d": now})
    tasks = c.fetchall()
    return render_template("index.html", tasks = tasks)

@app.route("/login", methods=["GET", "POST"])
def login():
    session.clear()
    if request.method == "POST":
        if not request.form.get("email"):
            flash("Must provide email")
            return render_template("login.html")
        elif not request.form.get("password"):
            flash("Must provide password")
            return render_template("login.html")
        email = request.form.get("email")
        conn = sqlite3.connect('data.db')
        c = conn.cursor()
        users = c.execute("SELECT * FROM users WHERE email = :email",
                          {"email": email.lower()})
        rows = c.fetchall()
        usercount = c.execute("SELECT COUNT(*) FROM users WHERE email = :email",
                          {"email": email.lower()})
        rowscount = c.fetchone()
        if rowscount[0] != 1 or not check_password_hash(rows[0][2], request.form.get("password")):
            flash("Invalid email and/or password")
            return render_template("login.html")
        session["user_id"] = rows[0][0]
        return redirect("/")
    else:
        return render_template("login.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "POST":
        if not request.form.get("email"):
            flash("Please write your email")
            return render_template("register.html")
        elif not request.form.get("password"):
            flash("Please create a password")
            return render_template("register.html")
        elif not request.form.get("confirmation"):
            flash("Please repeat your password")
            return render_template("register.html")
        elif request.form.get("password") != request.form.get("confirmation"):
            flash("Passwords do not match")
            return render_template("register.html")
        else:
            sk = 0
            r = 0
            a = 0
            psw = request.form.get("password")
            if len(psw) < 6:
                flash("Password should be at least 6 characters long")
                return render_template("register.html")
            for p in psw:
                if p.isdigit() == True:
                    sk += 1
                elif p.islower() == True:
                    r += 1
                elif p.isupper() == True:
                    a += 1
            if sk == 0 or r == 0 or a == 0:
                flash("Password should have at least one number, one uppercase and one lowercase letter")
                return render_template("register.html")
        email= request.form.get("email")
        conn = sqlite3.connect('data.db')
        c = conn.cursor()
        usercount = c.execute("SELECT COUNT(*) FROM users WHERE email = :email",{"email": email.lower()})
        rowscount = c.fetchone()
        users = c.execute("SELECT * FROM users WHERE email = :email",{"email": email.lower()})
        rows = c.fetchall()
        if rowscount[0] == 0:
            flash("You have no permission to register")
            return render_template("register.html")
        elif not rows[0][2] == None:
            flash("This account is already registered")
            return render_template("login.html")
        else:
            password_hash = generate_password_hash(request.form.get("password"))
            c.execute ("""UPDATE users
                        SET password = ?
                        WHERE email = ?""",
                        (password_hash, email.lower()))
            conn.commit()
            conn.close()
            flash("You can now log in!")
            return render_template("login.html")
    else:
        return render_template("register.html")

@app.route("/tasks")
@login_required
def tasks():
    conn = sqlite3.connect('data.db')
    c = conn.cursor()
    rows = c.execute("SELECT * FROM tasks ORDER BY deadline DESC")
    tasks = c.fetchall()
    return render_template("tasks.html", tasks=tasks)

@app.route("/edittask/<string:id>", methods=["GET", "POST"])
@login_required
def edittask(id):
    conn = sqlite3.connect('data.db')
    c = conn.cursor()
    rows = c.execute("SELECT * FROM tasks WHERE id = :id", {"id": id})
    rez = c.fetchone()
    if not rez == None:
        global taskid
        taskid = id
    if request.method == 'POST':
        task = request.form.get("task")
        responsible = request.form.get("responsible")
        status = request.form.get("status")
        year = request.form.get("year")
        month = request.form.get("month")
        day = request.form.get("day")
        date = "{}-{}-{}".format(year, month, day)
        date_obj = datetime.datetime.strptime(date, "%Y-%m-%d")
        c.execute ("""UPDATE tasks
                SET task=:t, responsible=:r, deadline=:d, status=:s
                WHERE id=:i""", {"t":task, "r":responsible, "d":date_obj.date(), "s":status, "i":taskid})
        rows = c.execute("SELECT * FROM tasks ORDER BY deadline DESC")
        tasks = c.fetchall()
        conn.commit()
        conn.close()
        flash("Task updated")
        return render_template("/tasks.html", tasks = tasks)
    else:
        rows = c.execute("SELECT * FROM tasks WHERE id = :id", {"id": id})
        data = c.fetchone()
        dt = datetime.datetime.strptime(data[3], "%Y-%m-%d")
        return render_template('edittask.html', data=data, dt=dt)

@app.route("/deletetask/<string:id>", methods=["GET", "POST"])
@login_required
def deletetask(id):
    conn = sqlite3.connect('data.db')
    c = conn.cursor()
    rows = c.execute("SELECT * FROM tasks WHERE id = ?", [id])
    rez = c.fetchone()
    if not rez == None:
        global taskid
        taskid = id
    if request.method == "POST":
        c.execute("DELETE FROM tasks WHERE id=?", [taskid])
        rows = c.execute("SELECT * FROM tasks ORDER BY deadline DESC")
        tasks = c.fetchall()
        conn.commit()
        conn.close()
        flash("Task deleted")
        return render_template("tasks.html", tasks = tasks)
    return render_template("deletetask.html")

@app.route("/newuser", methods=["GET", "POST"])
@login_required
def newuser():
    conn = sqlite3.connect('data.db')
    c = conn.cursor()
    rows = c.execute("SELECT * FROM users")
    users = c.fetchall()
    if request.method == "POST":
        if not request.form.get("email"):
            flash("Please write an email")
            return render_template("newuser.html")
        c.execute ("INSERT INTO users (email) VALUES (:email)", {"email": request.form.get("email").lower()})
        now = datetime.date.today()
        rows = c.execute("SELECT * FROM tasks WHERE deadline >= :d ORDER BY deadline ASC LIMIT 7",
                {"d": now})
        tasks = c.fetchall()
        conn.commit()
        conn.close()
        flash("This user can now register")
        return render_template("index.html", tasks=tasks)
    else:
        return render_template("newuser.html", users=users)

@app.route("/newtask", methods=["GET", "POST"])
@login_required
def newtask():
    if request.method == "POST":
        if not request.form.get("task"):
            flash("Please write a task")
            return render_template("newtask.html")
        elif not request.form.get("responsible"):
            flash("Please write who is responsible for the task")
            return render_template("newtask.html")
        elif int(request.form.get("year")) == 0 or int(request.form.get("month")) == 0 or int(request.form.get("day")) == 0:
            flash("Please write the full deadline")
            return render_template("newtask.html")
        task = request.form.get("task")
        responsible = request.form.get("responsible")
        year = request.form.get("year")
        month = request.form.get("month")
        day = request.form.get("day")
        date = "{}-{}-{}".format(year, month, day)
        date_obj = datetime.datetime.strptime(date, "%Y-%m-%d")
        conn = sqlite3.connect('data.db')
        c = conn.cursor()
        c.execute ("INSERT INTO tasks (task, responsible, deadline) VALUES (:task, :responsible, :deadline)",
            {"task": task, "responsible": responsible, "deadline": date_obj.date()})
        rows = c.execute("SELECT * FROM tasks ORDER BY deadline DESC")
        tasks = c.fetchall()
        conn.commit()
        conn.close()
        flash("Task added!")
        return render_template("tasks.html", tasks=tasks)
    else:
        return render_template("newtask.html")

@app.route('/forgot', methods=["GET", "POST"])
def forgot():
    if request.method == "POST":
        if not request.form.get("email"):
            flash("Please write your email")
            return render_template("forgot.html")
        else:
            n = 0
            email = request.form.get("email")
            conn = sqlite3.connect('data.db')
            c = conn.cursor()
            c.execute ("SELECT COUNT(*) FROM users WHERE email=:e", {"e": email})
            users = c.fetchone()
            if int(users[0]) != 0:
                password_reset_serializer = URLSafeTimedSerializer(app.config['SECRET_KEY'])
                password_reset_url = url_for('reset_with_token',
                        token = password_reset_serializer.dumps(email, salt='password-reset-salt'),
                        _external=True)
                SUBJECT = "Password reset"
                TEXT = "This is your password reset link:" + password_reset_url
                server = smtplib.SMTP_SSL("smtp.gmail.com", 465)
                message = 'Subject: {}\n\n{}'.format(SUBJECT, TEXT)
                server.login(app.config['email'], app.config['email_password'])
                server.sendmail("lkvatasks@gmail.com", email, message)
                server.quit()
                flash('Please check your email for a password reset link (could be in the spam folder)')
                return render_template("login.html")
            else:
                flash('This email is not registered')
                return render_template('forgot.html')
    return render_template("forgot.html")

@app.route('/reset/<token>', methods=["GET", "POST"])
def reset_with_token(token):
    try:
        password_reset_serializer = URLSafeTimedSerializer(app.config['SECRET_KEY'])
        email = password_reset_serializer.loads(token, salt='password-reset-salt', max_age=3600)
    except:
        flash('The password reset link is invalid or has expired')
        return redirect(url_for('login'))
    if request.method == "POST":
        if not request.form.get("password"):
            flash("Please enter your new password")
            return render_template('newpassword.html', token=token)
        elif not request.form.get("confirmation"):
            flash("Please repeat your new password")
            return render_template('newpassword.html', token=token)
        elif request.form.get("password") != request.form.get("confirmation"):
            flash("Passwords do not match")
            return render_template('newpassword.html', token=token)
        sk = 0
        r = 0
        a = 0
        psw = request.form.get("password")
        if len(psw) < 6:
            flash("Password should be at least 6 characters long")
            return render_template('newpassword.html', token=token)
        for p in psw:
            if p.isdigit() == True:
                sk += 1
            elif p.islower() == True:
                r += 1
            elif p.isupper() == True:
                a += 1
        if sk == 0 or r == 0 or a == 0:
            flash("Password should have at least one number, one uppercase and one lowercase letter")
            return render_template('newpassword.html', token=token)
        else:
            password_hash = generate_password_hash(request.form.get("password"))
            conn = sqlite3.connect('data.db')
            c = conn.cursor()
            c.execute ("""UPDATE users
                    SET password = ?
                    WHERE email = ?""",
                    (password_hash, email))
            conn.commit()
            conn.close()
            flash("Your password has been updated")
            return render_template("login.html")
    return render_template('newpassword.html', token=token)

@app.route("/delete", methods=["GET", "POST"])
@login_required
def delete():
    if request.method == "POST":
        conn = sqlite3.connect('data.db')
        c = conn.cursor()
        id = session["user_id"]
        print(id)
        c.execute("DELETE FROM users WHERE id=?", [id])
        conn.commit()
        conn.close()
        flash("User deleted")
        return render_template("login.html")
    return render_template("delete.html")

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/newfile', methods=['GET', 'POST'])
@login_required
def upload_file():
    if request.method == 'POST':
        file = request.files['file']
        if file.filename == '':
            flash('No selected file')
            return redirect(request.url)
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            conn = sqlite3.connect('data.db')
            c = conn.cursor()
            files = c.execute ("SELECT COUNT(*) FROM files WHERE name = :name", {"name": filename})
            count = c.fetchone()
            if not count[0] == 0:
                flash('File with the same name already exists: please change the name')
                return redirect(request.url)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            c.execute ("INSERT INTO files (name, notes) VALUES (:name, :notes)",
                {"name": filename, "notes": request.form.get("notes")})
            rows = c.execute("SELECT * FROM files ORDER BY id DESC")
            files = c.fetchall()
            conn.commit()
            conn.close()
            flash("File added!")
            return render_template("files.html", files = files)
        else:
            flash ("This type of file isn't supported")
            return redirect(request.url)
    return render_template("newfile.html")

@app.route('/files')
@login_required
def files():
    conn = sqlite3.connect('data.db')
    c = conn.cursor()
    rows = c.execute("SELECT * FROM files ORDER BY id DESC")
    files = c.fetchall()
    conn.commit()
    conn.close()
    return render_template("files.html", files=files)

@app.route('/files/<filename>')
@login_required
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'],
                               filename)

@app.route('/editfile/<string:id>', methods = ["GET", "POST"])
@login_required
def editfile(id):
    conn = sqlite3.connect('data.db')
    c = conn.cursor()
    rows = c.execute("SELECT * FROM files WHERE id = ?", [id])
    rez = c.fetchone()
    name = rez[1]
    if not rez == None:
        global fileid
        fileid = id
    if request.method == 'POST':
        notes = request.form.get("notes")
        status = request.form.get("status")
        file = request.files['file']
        if not file.filename == '':
            if file and allowed_file(file.filename):
                if file.filename == name:
                    if os.path.exists(UPLOAD_FOLDER + "/" + name):
                        os.remove(UPLOAD_FOLDER + "/" + name)
                        filename = secure_filename(file.filename)
                        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                        c.execute ("""UPDATE files
                            SET notes=:n, status=:s, name=:name
                            WHERE id=:i""", {"n":notes, "s":status, "name": filename,"i":fileid})
                else:
                    rows = c.execute("SELECT COUNT(*) FROM files WHERE name = ?", [file.filename])
                    rez = c.fetchone()
                    if not rez[0] == 0:
                        flash('File with the same name already exists: please change the name')
                        rows = c.execute("SELECT * FROM files WHERE id = ?", [id])
                        data = c.fetchone()
                        return render_template('editfile.html', data=data)
                    else:
                        if os.path.exists(UPLOAD_FOLDER + "/" + name):
                            os.remove(UPLOAD_FOLDER + "/" + name)
                            filename = secure_filename(file.filename)
                            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                            c.execute ("""UPDATE files
                                SET notes=:n, status=:s, name=:name
                                WHERE id=:i""", {"n":notes, "s":status, "name": filename,"i":fileid})
            else:
                flash ("This type of file isn't supported")
                rows = c.execute("SELECT * FROM files WHERE id = ?", [id])
                data = c.fetchone()
                return render_template('editfile.html', data=data)
        else:
            c.execute ("""UPDATE files
                SET notes=:n, status=:s
                WHERE id=:i""", {"n":notes, "s":status, "i":fileid})
        rows = c.execute("SELECT * FROM files ORDER BY id DESC")
        files = c.fetchall()
        conn.commit()
        conn.close()
        flash("File updated")
        return redirect(url_for("files", files = files))
    else:
        rows = c.execute("SELECT * FROM files WHERE id = ?", [id])
        data = c.fetchone()
        return render_template('editfile.html', data=data)

@app.route('/deletefile/<string:name>/', methods=['GET', 'POST'])
@login_required
def delete_item(name):
    if request.method == 'POST':
        if os.path.exists(UPLOAD_FOLDER + "/" + name):
            os.remove(UPLOAD_FOLDER + "/" + name)
            conn = sqlite3.connect('data.db')
            c = conn.cursor()
            rows = c.execute("DELETE FROM files WHERE name = :name", {"name": name})
            rez = c.fetchone()
            rows = c.execute("SELECT * FROM files ORDER BY id DESC")
            files = c.fetchall()
            conn.commit()
            conn.close()
            flash("File deleted!")
        return redirect(url_for("files"))
    return render_template("deletefile.html")

@app.route("/logout")
@login_required
def logout():
    session.clear()
    return redirect("/login")

if __name__ == "__main__":
    app.run(debug=True)
