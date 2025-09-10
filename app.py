# FILE: app.py
from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
import mysql.connector
from datetime import date, datetime
import os

app = Flask(__name__)
app.secret_key = os.environ.get("OEMSSK", "2004")  # replace for production

# MySQL config – set env vars or edit here
DB_CONFIG = {
    "host": os.environ.get("DB_HOST", "localhost"),
    "user": os.environ.get("DB_USER", "root"),
    "password": os.environ.get("DB_PASS", "Ashish@2004"),
    "database": os.environ.get("DB_NAME", "oems"),
}

def get_db():
    return mysql.connector.connect(**DB_CONFIG)

# ------------------ Helpers ------------------

def login_required(roles=None):
    def decorator(fn):
        def wrapper(*args, **kwargs):
            if "user" not in session:
                return redirect(url_for("login"))
            if roles and session["user"]["role"] not in roles:
                flash("Unauthorized.", "error")
                return redirect(url_for("dashboard"))
            return fn(*args, **kwargs)
        wrapper.__name__ = fn.__name__
        return wrapper
    return decorator

def current_user():
    return session.get("user")

# ------------------ Auth ------------------

@app.route("/init-passwords")
def init_passwords():
    # Convenience route to set real password hashes for seeded users.
    # admin/admin123, hr/hr123, ashish/ashish123
    conn = get_db()
    cur = conn.cursor()
    updates = [
        ("admin", generate_password_hash("admin123")),
        ("hr", generate_password_hash("hr123")),
        ("ashish", generate_password_hash("ashish123")),
    ]
    for u, h in updates:
        cur.execute("UPDATE users SET password_hash=%s WHERE username=%s", (h, u))
    conn.commit()
    cur.close()
    conn.close()
    return "Passwords initialized."

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username","").strip()
        password = request.form.get("password","")
        conn = get_db()
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM users WHERE username=%s", (username,))
        user = cur.fetchone()
        cur.close(); conn.close()
        if user and check_password_hash(user["password_hash"], password):
            session["user"] = {
                "user_id": user["user_id"],
                "username": user["username"],
                "role": user["role"],
                "employee_id": user["employee_id"],
            }
            return redirect(url_for("dashboard"))
        flash("Invalid credentials.", "error")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# ------------------ Dashboard ------------------

@app.route("/")
@login_required()
def dashboard():
    user = current_user()
    role = user["role"]

    stats = {}
    conn = get_db()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT COUNT(*) AS c FROM employees"); stats["employees"] = cur.fetchone()["c"]
    cur.execute("SELECT COUNT(*) AS c FROM departments"); stats["departments"] = cur.fetchone()["c"]
    cur.execute("SELECT COUNT(*) AS c FROM leave_requests WHERE status='Pending'"); stats["pending_leaves"] = cur.fetchone()["c"]

    if role == "EMPLOYEE" and user["employee_id"]:
        # Today attendance status
        cur.execute(
            "SELECT status FROM attendance WHERE employee_id=%s AND date=%s",
            (user["employee_id"], date.today())
        )
        row = cur.fetchone()
        stats["today_status"] = row["status"] if row else "Not Marked"
        # Last payroll
        cur.execute(
            "SELECT * FROM payroll WHERE employee_id=%s ORDER BY period_end DESC LIMIT 1",
            (user["employee_id"],)
        )
        stats["last_payroll"] = cur.fetchone()
    cur.close(); conn.close()

    return render_template("dashboard.html", stats=stats, role=role)

# ------------------ Departments ------------------

@app.route("/departments")
@login_required(roles=["ADMIN","HR"])
def departments():
    conn = get_db()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM departments ORDER BY department_name")
    items = cur.fetchall()
    cur.close(); conn.close()
    return render_template("departments.html", items=items)

@app.route("/departments/add", methods=["POST"])
@login_required(roles=["ADMIN","HR"])
def add_department():
    name = request.form.get("department_name","").strip()
    if not name:
        flash("Department name required.", "error")
        return redirect(url_for("departments"))
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("INSERT INTO departments (department_name) VALUES (%s)", (name,))
        conn.commit()
        flash("Department added.", "success")
    except mysql.connector.Error as e:
        flash(f"Error: {e.msg}", "error")
    finally:
        cur.close(); conn.close()
    return redirect(url_for("departments"))

@app.route("/departments/delete/<int:dept_id>", methods=["POST"])
@login_required(roles=["ADMIN","HR"])
def delete_department(dept_id):
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM departments WHERE department_id=%s", (dept_id,))
        conn.commit()
        flash("Department deleted.", "success")
    except mysql.connector.Error as e:
        flash(f"Error: {e.msg}", "error")
    finally:
        cur.close(); conn.close()
    return redirect(url_for("departments"))

# ------------------ Employees ------------------

@app.route("/employees")
@login_required(roles=["ADMIN","HR"])
def employees():
    conn = get_db()
    cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT e.*, d.department_name
        FROM employees e
        LEFT JOIN departments d ON e.department_id=d.department_id
        ORDER BY e.employee_id DESC
    """)
    items = cur.fetchall()
    cur.execute("SELECT * FROM departments ORDER BY department_name")
    depts = cur.fetchall()
    cur.close(); conn.close()
    return render_template("employees.html", items=items, depts=depts)

@app.route("/employees/add", methods=["POST"])
@login_required(roles=["ADMIN","HR"])
def add_employee():
    name = request.form.get("name","").strip()
    email = request.form.get("email","").strip()
    phone = request.form.get("phone","").strip()
    position = request.form.get("position","").strip()
    department_id = request.form.get("department_id")
    salary = request.form.get("salary","0").strip()

    if not name or not email:
        flash("Name and email required.", "error")
        return redirect(url_for("employees"))
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO employees (name,email,phone,position,department_id,salary) VALUES (%s,%s,%s,%s,%s,%s)",
            (name,email,phone,position,department_id if department_id else None, salary or 0)
        )
        conn.commit()
        flash("Employee added.", "success")
    except mysql.connector.Error as e:
        flash(f"Error: {e.msg}", "error")
    finally:
        cur.close(); conn.close()
    return redirect(url_for("employees"))

@app.route("/employees/update/<int:employee_id>", methods=["POST"])
@login_required(roles=["ADMIN","HR"])
def update_employee(employee_id):
    name = request.form.get("name","").strip()
    phone = request.form.get("phone","").strip()
    position = request.form.get("position","").strip()
    department_id = request.form.get("department_id")
    salary = request.form.get("salary","0").strip()
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("""
            UPDATE employees
            SET name=%s, phone=%s, position=%s, department_id=%s, salary=%s
            WHERE employee_id=%s
        """, (name,phone,position,department_id if department_id else None,salary or 0, employee_id))
        conn.commit()
        flash("Employee updated.", "success")
    except mysql.connector.Error as e:
        flash(f"Error: {e.msg}", "error")
    finally:
        cur.close(); conn.close()
    return redirect(url_for("employees"))

@app.route("/employees/delete/<int:employee_id>", methods=["POST"])
@login_required(roles=["ADMIN","HR"])
def delete_employee(employee_id):
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM employees WHERE employee_id=%s", (employee_id,))
        conn.commit()
        flash("Employee deleted.", "success")
    except mysql.connector.Error as e:
        flash(f"Error: {e.msg}", "error")
    finally:
        cur.close(); conn.close()
    return redirect(url_for("employees"))

# ------------------ Attendance ------------------

@app.route("/attendance", methods=["GET","POST"])
@login_required()
def attendance():
    user = current_user()
    conn = get_db()
    cur = conn.cursor(dictionary=True)

    if request.method == "POST":
        # Mark attendance for current user (EMPLOYEE) or on behalf (HR/ADMIN)
        target_emp = user["employee_id"]
        if user["role"] in ("ADMIN","HR"):
            target_emp = int(request.form.get("employee_id"))
        status = request.form.get("status","Present")
        today = date.today()
        try:
            cur.execute("""
                INSERT INTO attendance (employee_id, date, status)
                VALUES (%s,%s,%s)
                ON DUPLICATE KEY UPDATE status=VALUES(status)
            """, (target_emp, today, status))
            conn.commit()
            flash("Attendance recorded.", "success")
        except mysql.connector.Error as e:
            flash(f"Error: {e.msg}", "error")

    # Data for view
    if user["role"] in ("ADMIN","HR"):
        cur.execute("""
            SELECT a.attendance_id, a.date, a.status, e.name
            FROM attendance a
            JOIN employees e ON a.employee_id=e.employee_id
            ORDER BY a.date DESC LIMIT 50
        """)
        records = cur.fetchall()
        cur.execute("SELECT employee_id, name FROM employees ORDER BY name")
        emps = cur.fetchall()
    else:
        cur.execute("""
            SELECT a.attendance_id, a.date, a.status
            FROM attendance a
            WHERE a.employee_id=%s
            ORDER BY a.date DESC LIMIT 50
        """, (user["employee_id"],))
        records = cur.fetchall()
        emps = []

    cur.close(); conn.close()
    return render_template("attendance.html", records=records, emps=emps)

# ------------------ Leaves ------------------

@app.route("/leaves", methods=["GET","POST"])
@login_required()
def leaves():
    user = current_user()
    conn = get_db()
    cur = conn.cursor(dictionary=True)

    if request.method == "POST" and user["role"] == "EMPLOYEE":
        start_date = request.form.get("start_date")
        end_date = request.form.get("end_date")
        try:
            cur.execute("""
                INSERT INTO leave_requests (employee_id,start_date,end_date,status)
                VALUES (%s,%s,%s,'Pending')
            """, (user["employee_id"], start_date, end_date))
            conn.commit()
            flash("Leave requested.", "success")
        except mysql.connector.Error as e:
            flash(f"Error: {e.msg}", "error")

    if user["role"] in ("ADMIN","HR"):
        cur.execute("""
            SELECT l.leave_id, l.start_date, l.end_date, l.status, e.name
            FROM leave_requests l
            JOIN employees e ON l.employee_id=e.employee_id
            ORDER BY l.leave_id DESC LIMIT 100
        """)
        leaves = cur.fetchall()
    else:
        cur.execute("""
            SELECT l.leave_id, l.start_date, l.end_date, l.status
            FROM leave_requests l
            WHERE l.employee_id=%s
            ORDER BY l.leave_id DESC LIMIT 100
        """, (user["employee_id"],))
        leaves = cur.fetchall()
    cur.close(); conn.close()
    return render_template("leaves.html", leaves=leaves)

@app.route("/leaves/act/<int:leave_id>/<string:action>", methods=["POST"])
@login_required(roles=["ADMIN","HR"])
def act_leave(leave_id, action):
    if action not in ("Approved","Rejected"):
        flash("Invalid action.", "error")
        return redirect(url_for("leaves"))
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("UPDATE leave_requests SET status=%s WHERE leave_id=%s", (action, leave_id))
        conn.commit()
        flash(f"Leave {action.lower()}.", "success")
    except mysql.connector.Error as e:
        flash(f"Error: {e.msg}", "error")
    finally:
        cur.close(); conn.close()
    return redirect(url_for("leaves"))

# ------------------ Payroll ------------------

@app.route("/payroll", methods=["GET","POST"])
@login_required(roles=["ADMIN","HR","EMPLOYEE"])
def payroll_view():
    user = current_user()
    conn = get_db()
    cur = conn.cursor(dictionary=True)

    if request.method == "POST" and user["role"] in ("ADMIN","HR"):
        employee_id = int(request.form.get("employee_id"))
        period_start = request.form.get("period_start")
        period_end = request.form.get("period_end")
        deductions = float(request.form.get("deductions","0") or 0)
        bonuses = float(request.form.get("bonuses","0") or 0)

        # Fetch base salary and working days attendance
        cur.execute("SELECT salary FROM employees WHERE employee_id=%s", (employee_id,))
        emp = cur.fetchone()
        if not emp:
            flash("Employee not found.", "error")
        else:
            basic_salary = float(emp["salary"])
            # Simple rule: if any 'Absent' in period, deduct 1 day per absence from monthly 30-day basis
            cur.execute("""
                SELECT SUM(CASE WHEN status='Absent' THEN 1 ELSE 0 END) AS absences
                FROM attendance
                WHERE employee_id=%s AND date BETWEEN %s AND %s
            """, (employee_id, period_start, period_end))
            row = cur.fetchone()
            absences = int(row["absences"] or 0)
            per_day = basic_salary / 30.0
            auto_ded = per_day * absences
            total_deductions = deductions + auto_ded
            net_salary = max(0.0, basic_salary - total_deductions + bonuses)

            try:
                cur.execute("""
                    INSERT INTO payroll (employee_id,period_start,period_end,basic_salary,deductions,bonuses,net_salary)
                    VALUES (%s,%s,%s,%s,%s,%s,%s)
                    ON DUPLICATE KEY UPDATE
                      basic_salary=VALUES(basic_salary),
                      deductions=VALUES(deductions),
                      bonuses=VALUES(bonuses),
                      net_salary=VALUES(net_salary)
                """, (employee_id, period_start, period_end, basic_salary, total_deductions, bonuses, net_salary))
                conn.commit()
                flash("Payroll generated.", "success")
            except mysql.connector.Error as e:
                flash(f"Error: {e.msg}", "error")

    if user["role"] in ("ADMIN","HR"):
        cur.execute("""
            SELECT p.*, e.name
            FROM payroll p
            JOIN employees e ON p.employee_id=e.employee_id
            ORDER BY p.period_end DESC
        """)
        items = cur.fetchall()
        cur.execute("SELECT employee_id, name FROM employees ORDER BY name")
        emps = cur.fetchall()
    else:
        cur.execute("""
            SELECT p.* FROM payroll p
            WHERE p.employee_id=%s
            ORDER BY p.period_end DESC
        """, (user["employee_id"],))
        items = cur.fetchall()
        emps = []

    cur.close(); conn.close()
    return render_template("payroll.html", items=items, emps=emps)

@app.route("/payroll/payslip/<int:payroll_id>")
@login_required()
def payslip(payroll_id):
    user = current_user()
    conn = get_db()
    cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT p.*, e.name, e.position, e.email
        FROM payroll p
        JOIN employees e ON p.employee_id=e.employee_id
        WHERE p.payroll_id=%s
    """, (payroll_id,))
    item = cur.fetchone()
    cur.close(); conn.close()

    if not item:
        flash("Payslip not found.", "error")
        return redirect(url_for("payroll_view"))

    # Access control: employee can view own, HR/Admin can view all
    if user["role"] == "EMPLOYEE" and current_user()["employee_id"] != item["employee_id"]:
        flash("Unauthorized.", "error")
        return redirect(url_for("payroll_view"))

    return render_template("payslip.html", item=item)

# ------------------ Reports ------------------

@app.route("/reports")
@login_required(roles=["ADMIN","HR"])
def reports():
    conn = get_db()
    cur = conn.cursor(dictionary=True)

    # Attendance summary by employee (last 30 days)
    cur.execute("""
        SELECT e.employee_id, e.name,
               SUM(a.status='Present') AS present_days,
               SUM(a.status='Absent')  AS absent_days,
               SUM(a.status='Leave')   AS leave_days
        FROM employees e
        LEFT JOIN attendance a ON a.employee_id=e.employee_id
          AND a.date >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)
        GROUP BY e.employee_id, e.name
        ORDER BY e.name
    """)
    attendance_summary = cur.fetchall()

    # Payroll summary last 3 periods
    cur.execute("""
        SELECT e.name, p.*
        FROM payroll p
        JOIN employees e ON p.employee_id=e.employee_id
        ORDER BY p.period_end DESC
        LIMIT 50
    """)
    payroll_recent = cur.fetchall()

    cur.close(); conn.close()
    return render_template("reports.html", attendance_summary=attendance_summary, payroll_recent=payroll_recent)

# ------------------ Profile (Employee self-service) ------------------

@app.route("/profile", methods=["GET","POST"])
@login_required()
def profile():
    user = current_user()
    emp_id = user.get("employee_id")
    if not emp_id:
        flash("No employee profile linked.", "error")
        return redirect(url_for("dashboard"))

    conn = get_db()
    cur = conn.cursor(dictionary=True)

    if request.method == "POST":
        name = request.form.get("name","").strip()
        phone = request.form.get("phone","").strip()
        try:
            cur.execute("UPDATE employees SET name=%s, phone=%s WHERE employee_id=%s", (name, phone, emp_id))
            conn.commit()
            flash("Profile updated.", "success")
        except mysql.connector.Error as e:
            flash(f"Error: {e.msg}", "error")

    cur.execute("""
        SELECT e.*, d.department_name
        FROM employees e
        LEFT JOIN departments d ON e.department_id=d.department_id
        WHERE e.employee_id=%s
    """, (emp_id,))
    emp = cur.fetchone()
    cur.close(); conn.close()
    return render_template("profile.html", emp=emp)

# ------------------ Run ------------------

if _name_ == "_main_":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
