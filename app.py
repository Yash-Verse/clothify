import os
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
import pyodbc
from werkzeug.utils import secure_filename
from datetime import datetime
from flask import request


# =========================================================
# FLASK CONFIG
# =========================================================
app = Flask(__name__)
app.secret_key = "clothstore123"

# =========================================================
# SQL SERVER CONFIG
# =========================================================
SERVER = r"ASUSTUFGAMING\SQLEXPRESS"
DATABASE = "cloth_store"
DRIVER = "{ODBC Driver 17 for SQL Server}"

def get_conn():
    return pyodbc.connect(
        f"DRIVER={DRIVER};SERVER={SERVER};DATABASE={DATABASE};Trusted_Connection=yes;"
    )

# Convert DB rows → dicts
def rows_to_dicts(cursor):
    cols = [col[0] for col in cursor.description]
    return [dict(zip(cols, row)) for row in cursor.fetchall()]

# =========================================================
# IMAGE UPLOAD CONFIG
# =========================================================
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "static", "images", "products")
os.makedirs(UPLOAD_DIR, exist_ok=True)

ALLOWED_EXT = {"png", "jpg", "jpeg", "gif", "webp"}

def allowed_filename(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXT

# =========================================================
# GLOBAL TEMPLATE VARIABLES
# =========================================================
@app.context_processor
def inject_globals():
    # Provide session_user as object/dict with username property so templates using
    # session_user.username continue to work even though we store just a string.
    user = session.get("user")
    session_user = {"username": user} if user else None
    return {
        "now": datetime.utcnow,
        "session_user": session_user,
        "current_year": datetime.utcnow().year
    }

# =========================================================
# LOGIN SYSTEM
# =========================================================
@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        uname = request.form["username"]
        pwd   = request.form["password"]

        if uname == "admin" and pwd == "admin123":
            # store username string - templates expect session_user.username
            session["user"] = "admin"
            flash("Login successful", "success")
            return redirect(url_for("home"))

        flash("Invalid username or password", "danger")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


def login_required(fn):
    def wrapper(*args, **kwargs):
        if not session.get("user"):
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    wrapper.__name__ = fn.__name__
    return wrapper


# =========================================================
# HOME PAGE (only active products)
# =========================================================
@app.route("/")
@login_required
def home():
    conn = get_conn()
    cur = conn.cursor()

    q = request.args.get("q") or ""

    if q:
        cur.execute("""
            SELECT p.id, p.name, p.price, p.quantity, p.colour, p.brand,
                   c.name AS category, p.image_url
            FROM products p
            LEFT JOIN categories c ON p.category_id = c.id
            WHERE (p.name LIKE ? OR p.brand LIKE ?)
              AND ISNULL(p.is_deleted, 0) = 0
        """, (f"%{q}%", f"%{q}%"))
    else:
        cur.execute("""
            SELECT p.id, p.name, p.price, p.quantity, p.colour, p.brand,
                   c.name AS category, p.image_url
            FROM products p
            LEFT JOIN categories c ON p.category_id = c.id
            WHERE ISNULL(p.is_deleted, 0) = 0
        """)

    products = rows_to_dicts(cur)
    print("PRODUCTS LOADED:", products)   # <--- ADD THIS
    cur.execute("SELECT * FROM categories")
    categories = rows_to_dicts(cur)

    cur.close()
    conn.close()

    return render_template("home.html", products=products, categories=categories, q=q)


# =========================================================
# SUPPLIERS CRUD
# =========================================================

@app.route("/suppliers")
@login_required
def suppliers_page():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM suppliers ORDER BY id DESC")
    suppliers = rows_to_dicts(cur)
    cur.close(); conn.close()

    return render_template("suppliers.html", suppliers=suppliers)


@app.route("/suppliers/add", methods=["GET", "POST"])
@login_required
def supplier_add():
    if request.method == "POST":
        name = request.form.get("name")
        contact = request.form.get("contact")
        address = request.form.get("address")
        date_added = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')

        conn = get_conn()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO suppliers (name, contact, address, date_added)
            VALUES (?, ?, ?, ?)
        """, (name, contact, address, date_added))

        conn.commit()
        cur.close(); conn.close()

        flash("Supplier added successfully", "success")
        return redirect(url_for("suppliers_page"))

    return render_template("supplier_form.html", supplier=None)


@app.route("/suppliers/edit/<int:id>", methods=["GET", "POST"])
@login_required
def supplier_edit(id):
    conn = get_conn()
    cur = conn.cursor()

    if request.method == "POST":
        name = request.form.get("name")
        contact = request.form.get("contact")
        address = request.form.get("address")

        cur.execute("""
            UPDATE suppliers
            SET name=?, contact=?, address=?
            WHERE id=?
        """, (name, contact, address, id))

        conn.commit()
        cur.close(); conn.close()

        flash("Supplier updated successfully", "success")
        return redirect(url_for("suppliers_page"))

    cur.execute("SELECT * FROM suppliers WHERE id=?", (id,))
    row = cur.fetchone()
    supplier = dict(zip([c[0] for c in cur.description], row))

    cur.close(); conn.close()

    return render_template("supplier_form.html", supplier=supplier)


@app.route("/suppliers/delete/<int:id>", methods=["POST"])
@login_required
def supplier_delete(id):
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("DELETE FROM suppliers WHERE id=?", (id,))
    conn.commit()

    cur.close(); conn.close()

    flash("Supplier deleted", "info")
    return redirect(url_for("suppliers_page"))

# =========================================================
# SUPPLIER → PRODUCTS VIEW (only active products)
# =========================================================
@app.route("/suppliers/<int:sid>/products")
@login_required
def supplier_products(sid):
    conn = get_conn()
    cur = conn.cursor()

    # Load supplier details
    cur.execute("SELECT * FROM suppliers WHERE id=?", (sid,))
    row = cur.fetchone()
    supplier = dict(zip([c[0] for c in cur.description], row))

    # Load all products belonging to this supplier (only not-deleted)
    cur.execute("""
        SELECT p.id, p.name, p.price, p.quantity, p.brand, p.colour, p.image_url,
               c.name AS category
        FROM products p
        LEFT JOIN categories c ON p.category_id = c.id
        WHERE p.supplier_id = ?
          AND ISNULL(p.is_deleted, 0) = 0
    """, (sid,))
    products = rows_to_dicts(cur)

    cur.close()
    conn.close()

    return render_template("supplier_products.html",
                           supplier=supplier,
                           products=products)


# =========================================================
# INVENTORY PAGE (only active products)
# =========================================================
@app.route("/inventory")
@login_required
def inventory():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        SELECT 
            p.id,
            p.name,
            p.price,
            p.quantity,
            p.is_deleted,
            c.name AS category
        FROM products p
        LEFT JOIN categories c ON p.category_id = c.id
        WHERE p.is_deleted = 0
    """)
    
    products = rows_to_dicts(cur)

    cur.close()
    conn.close()

    return render_template("inventory.html", products=products)



# =========================================================
# ADD PRODUCT
# =========================================================
@app.route("/product/add", methods=["GET","POST"])
@login_required
def add_product():
    conn = get_conn()
    cur = conn.cursor()

    if request.method == "POST":
        image_url = request.form.get("image_url")

        file = request.files.get("image_file")
        if file and file.filename:
            if allowed_filename(file.filename):
                fname = secure_filename(file.filename)
                unique_name = f"{int(datetime.utcnow().timestamp())}_{fname}"
                file_path = os.path.join(UPLOAD_DIR, unique_name)
                file.save(file_path)
                image_url = f"/static/images/products/{unique_name}"

        d = request.form

        cur.execute("""
            INSERT INTO products
            (name, price, quantity, category_id, colour, brand, description, image_url, supplier_id, is_deleted)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
        """, (
            d.get("name"), d.get("price"), d.get("quantity"),
            d.get("category_id") or None, d.get("colour"),
            d.get("brand"), d.get("description"), image_url,
            d.get("supplier_id") or None
        ))

        conn.commit()
        flash("Product added successfully", "success")
        return redirect(url_for("inventory"))

    cur.execute("SELECT * FROM categories")
    categories = rows_to_dicts(cur)

    cur.execute("SELECT * FROM suppliers")
    suppliers = rows_to_dicts(cur)

    cur.close()
    conn.close()

    return render_template("product_form.html", product=None, categories=categories, suppliers=suppliers)


# =========================================================
# EDIT PRODUCT
# =========================================================
@app.route("/product/edit/<int:pid>", methods=["GET","POST"])
@login_required
def edit_product(pid):
    conn = get_conn()
    cur = conn.cursor()

    if request.method == "POST":
        image_url = request.form.get("image_url")

        file = request.files.get("image_file")
        if file and file.filename:
            if allowed_filename(file.filename):
                fname = secure_filename(file.filename)
                unique_name = f"{int(datetime.utcnow().timestamp())}_{fname}"
                file_path = os.path.join(UPLOAD_DIR, unique_name)
                file.save(file_path)
                image_url = f"/static/images/products/{unique_name}"

        d = request.form

        # Before updating, you might want to log old values via trigger / app if required.
        cur.execute("""
            UPDATE products
            SET name=?, price=?, quantity=?, category_id=?, colour=?, brand=?,
                description=?, image_url=?, supplier_id=?
            WHERE id=?
        """, (
            d.get("name"), d.get("price"), d.get("quantity"),
            d.get("category_id") or None, d.get("colour"),
            d.get("brand"), d.get("description"), image_url,
            d.get("supplier_id") or None, pid
        ))

        conn.commit()
        flash("Product updated successfully", "success")
        return redirect(url_for("inventory"))

    cur.execute("SELECT * FROM products WHERE id=?", (pid,))
    row = cur.fetchone()
    product = dict(zip([c[0] for c in cur.description], row)) if row else None

    cur.execute("SELECT * FROM categories")
    categories = rows_to_dicts(cur)

    cur.execute("SELECT * FROM suppliers")
    suppliers = rows_to_dicts(cur)

    cur.close()
    conn.close()

    return render_template("product_form.html", product=product, categories=categories, suppliers=suppliers)


# =========================================================
# SOFT DELETE PRODUCT
# =========================================================
@app.route("/product/delete/<int:pid>", methods=["POST"])
@login_required
def delete_product(pid):
    conn = get_conn()
    cur = conn.cursor()

    # Soft-delete: set is_deleted = 1
    cur.execute("""
        UPDATE products
        SET is_deleted = 1
        WHERE id=?
    """, (pid,))

    # Also insert a record into Product_Deleted_Log so /products/deleted can show it
    # If you already implemented a trigger that logs deletes, remove this INSERT or adjust trigger
    # to avoid duplicate log rows.
    cur.execute("SELECT id, name, price, quantity, image_url FROM products WHERE id=?", (pid,))
    row = cur.fetchone()
    if row:
        prod = dict(zip([c[0] for c in cur.description], row))
        deleted_on = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        try:
            cur.execute("""
                INSERT INTO Product_Deleted_Log (product_id, name, price, quantity, deleted_on)
                VALUES (?, ?, ?, ?, ?)
            """, (prod["id"], prod["name"], prod["price"], prod["quantity"], deleted_on))
        except Exception:
            # swallow logging errors (e.g. log table missing) but continue
            pass

    conn.commit()
    cur.close()
    conn.close()

    flash("Product moved to Deleted Products", "info")
    return redirect(url_for("inventory"))


# =========================================================
# RESTORE SOFT-DELETED PRODUCT
# =========================================================
@app.route("/product/restore/<int:pid>", methods=["POST"])
@login_required
def restore_product(pid):
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("UPDATE products SET is_deleted = 0 WHERE id=?", (pid,))

    conn.commit()
    cur.close(); conn.close()

    flash("Product restored successfully!", "success")
    return redirect(url_for("deleted_products"))


# =========================================================
# DISPLAY DELETED PRODUCTS (reads Product_Deleted_Log)
# =========================================================
@app.route("/products/deleted")
@login_required
def deleted_products():
    conn = get_conn()
    cur = conn.cursor()

    # If you prefer to list current products with is_deleted = 1, you can replace this
    # SELECT with a query on products. Currently we read Product_Deleted_Log for historical entries.
    cur.execute("""
        SELECT * FROM Product_Deleted_Log ORDER BY deleted_on DESC
    """)
    deleted = rows_to_dicts(cur)

    cur.close()
    conn.close()

    return render_template("deleted_products.html", deleted=deleted)


# =========================================================
# DISPLAY UPDATED PRODUCTS LOG
# =========================================================
@app.route("/products/updates")
@login_required
def updated_products():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        SELECT * FROM Product_Update_Log ORDER BY updated_on DESC
    """)
    logs = rows_to_dicts(cur)

    cur.close()
    conn.close()

    return render_template("updated_products.html", logs=logs)


# =========================================================
# CATEGORIES WITH PRODUCT QUANTITIES
# =========================================================
@app.route("/categories", methods=["GET","POST"])
@login_required
def categories_page():
    conn = get_conn()
    cur = conn.cursor()

    if request.method == "POST":
        name = request.form.get("name")
        cur.execute("INSERT INTO categories (name) VALUES (?)", (name,))
        conn.commit()
        return redirect(url_for("categories_page"))

    cur.execute("""
        SELECT 
            c.id,
            c.name,
            COUNT(p.id) AS total_products,
            ISNULL(SUM(p.quantity), 0) AS total_quantity
        FROM categories c
        LEFT JOIN products p ON p.category_id = c.id AND ISNULL(p.is_deleted, 0) = 0
        GROUP BY c.id, c.name
        ORDER BY c.name
    """)
    categories = rows_to_dicts(cur)

    cur.close()
    conn.close()

    return render_template("categories.html", categories=categories)


# =========================================================
# BILLING PAGE
# =========================================================
@app.route("/billing")
@login_required
def billing():
    bill_items = session.get("bill_items", [])
    total = sum(float(i["subtotal"]) for i in bill_items)
    return render_template("billing.html", bill_items=bill_items, total_amount=total)


@app.route("/bill/add/<int:pid>")
@login_required
def bill_add(pid):
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("SELECT * FROM products WHERE id=?", (pid,))
    p = cur.fetchone()
    p = dict(zip([c[0] for c in cur.description], p))

    item = {
        "id": p["id"],
        "name": p["name"],
        "unit_price": float(p["price"]),
        "qty": 1,
        "subtotal": float(p["price"])
    }

    items = session.get("bill_items", [])
    items.append(item)
    session["bill_items"] = items

    cur.close()
    conn.close()

    return redirect(url_for("billing"))


# =========================================================
# SAVE BILL + AUTO REDUCE STOCK
# =========================================================
@app.route("/bill/save", methods=["POST"])
@login_required
def bill_save():
    items = request.json.get("items")
    if not items:
        return jsonify({"success": False})

    conn = get_conn()
    cur = conn.cursor()

    total = sum(float(x["subtotal"]) for x in items)

    # Insert into Billing table
    cur.execute("INSERT INTO Billing (customer_id, total_amount) VALUES (?,?)",
                (None, total))

    # Get inserted bill ID
    cur.execute("SELECT @@IDENTITY")
    bill_id = int(cur.fetchone()[0])

    # Insert bill items + reduce stock
    for item in items:
        cur.execute("""
            INSERT INTO BillItems (bill_id, product_id, unit_price, quantity, subtotal)
            VALUES (?, ?, ?, ?, ?)
        """, (
            bill_id,
            item["id"],
            item["unit_price"],
            item["qty"],
            item["subtotal"]
        ))

        # AUTO REDUCE STOCK
        cur.execute("SELECT quantity FROM products WHERE id=?", (item["id"],))
        current_qty = cur.fetchone()[0] or 0

        new_qty = max(0, current_qty - item["qty"])

        cur.execute("UPDATE products SET quantity=? WHERE id=?", (new_qty, item["id"]))

    conn.commit()
    cur.close()
    conn.close()

    session["bill_items"] = []

    return jsonify({"success": True, "bill_id": bill_id})


# =========================================================
# START SERVER
# =========================================================
if __name__ == "__main__":
    app.run(debug=True)
