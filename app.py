from flask import Flask, render_template, request, redirect, url_for
import sqlite3
from datetime import datetime
import os

app = Flask(__name__)
DATABASE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'database.db')

def init_db():
    database_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'database.db')
    print(f"Initializing database at: {database_path}")
    conn = sqlite3.connect(database_path)
    c = conn.cursor()
    # Comment out DROP TABLE to preserve data for testing
    # c.execute('''DROP TABLE IF EXISTS payments''')
    c.execute('''CREATE TABLE IF NOT EXISTS payments 
                 (id INTEGER PRIMARY KEY, username TEXT, amount REAL, city TEXT, timestamp TEXT)''')
    conn.commit()
    conn.close()

sweden_cities = [
    "Stockholm", "Gothenburg", "Malmö", "Uppsala", "Linköping", "Örebro", 
    "Västerås", "Helsingborg", "Norrköping", "Jönköping", "Other"
]

@app.route('/')
def index():
    conn = sqlite3.connect(DATABASE_PATH)
    c = conn.cursor()

    # Pagination parameters
    items_per_page = 10  # Configurable number of entries per page
    player_page = int(request.args.get('player_page', 1))  # Default to page 1
    city_page = int(request.args.get('city_page', 1))      # Default to page 1
    player_offset = (player_page - 1) * items_per_page
    city_offset = (city_page - 1) * items_per_page

    # Individual leaderboard with pagination

    c.execute("""
        SELECT username, (
            SELECT city 
            FROM payments p2 
            WHERE p2.username = p1.username 
            ORDER BY p2.timestamp DESC 
            LIMIT 1
        ), SUM(amount) 
        FROM payments p1 
        GROUP BY username 
        ORDER BY SUM(amount) DESC 
        LIMIT ? OFFSET ?
    """, (items_per_page, player_offset))

    # Add emoji based on total amount
    leaderboard = [
        (i + 1 + player_offset, 
        "👑 " + row[0] if row[2] >= 1000 else "💎 " + row[0] if row[2] >= 500 else row[0], 
        row[1], row[2]) 
        for i, row in enumerate(c.fetchall())
    ]

    # Total number of players for pagination
    c.execute("SELECT COUNT(DISTINCT username) FROM payments")
    total_players = c.fetchone()[0]
    total_player_pages = (total_players + items_per_page - 1) // items_per_page

    # City leaderboard with pagination
    c.execute("""
        SELECT city, COUNT(*) as donation_count, SUM(amount) 
        FROM payments 
        WHERE city IS NOT NULL 
        GROUP BY city 
        ORDER BY SUM(amount) DESC 
        LIMIT ? OFFSET ?
    """, (items_per_page, city_offset))
    city_leaderboard = [(i + 1 + city_offset, row[0], row[1], row[2]) for i, row in enumerate(c.fetchall())]

    # Total number of cities for pagination
    c.execute("SELECT COUNT(DISTINCT city) FROM payments WHERE city IS NOT NULL")
    total_cities = c.fetchone()[0]
    total_city_pages = (total_cities + items_per_page - 1) // items_per_page

    conn.close()
    return render_template('index.html', leaderboard=leaderboard, city_leaderboard=city_leaderboard, 
                           cities=sweden_cities, player_page=player_page, city_page=city_page, 
                           total_player_pages=total_player_pages, total_city_pages=total_city_pages)

@app.route('/faq')
def faq():
    return render_template('faq.html')

@app.route('/privacy-policy')
def privacy_policy():
    return render_template('privacy_policy.html')

@app.route('/disclaimer')
def disclaimer():
    return render_template('disclaimer.html')

@app.route('/payment-success')
def payment_success():
    username = request.args.get('username')
    amount = request.args.get('amount')
    city = request.args.get('city')

    error = request.args.get('error')
    error_message = None
    if error == 'amount_too_small':
        error_message = "The amount must be at least 1 SEK"

    conn = sqlite3.connect(DATABASE_PATH)
    c = conn.cursor()

    c.execute("SELECT username, amount FROM payments ORDER BY amount DESC")
    leaderboard = c.fetchall()

    c.execute("""
        SELECT city, COUNT(*) as donation_count, SUM(amount) 
        FROM payments 
        WHERE city IS NOT NULL 
        GROUP BY city 
        ORDER BY SUM(amount) DESC
    """)
    city_leaderboard = [(i + 1, row[0], row[1], row[2]) for i, row in enumerate(c.fetchall())]

    rank = None
    for index, entry in enumerate(leaderboard):
        if entry[0] == username:
            rank = index + 1
            break

    conn.close()
    return render_template('payment_success.html', username=username, amount=amount, 
                           city=city, error_message=error_message, rank=rank, city_leaderboard=city_leaderboard)

@app.route('/pay', methods=['POST'])
def pay():
    username = request.form['username']
    amount = float(request.form['amount'])
    city = request.form.get('city')

    if city == 'None' or not city:
        city = None

    return redirect(url_for('payment_page', username=username, amount=amount, city=city))

@app.route('/payment')
def payment_page():
    username = request.args.get('username')
    amount = request.args.get('amount')
    city = request.args.get('city')
    return render_template('payment.html', username=username, amount=amount, city=city)

@app.route('/process-payment', methods=['POST'])
def process_payment():
    username = request.form.get('username')
    amount = request.form.get('amount')
    city = request.form.get('city')
    payment_method = request.form.get('payment_method')

    if not username or not amount:
        return redirect(url_for('payment_page', error="Missing required fields"))

    try:
        amount = float(amount)
        if amount < 1:
            return redirect(url_for('payment_success', username=username, amount=amount, city=city, error='amount_too_small'))
    except ValueError:
        return redirect(url_for('payment_page', error="Invalid amount"))

    # Process based on payment method
    if payment_method == "Swish":
        phone = request.form.get('phone')
        if not phone:
            return redirect(url_for('payment_page', error="Phone number is required for Swish"))

    elif payment_method == "Credit Card":
        card_number = request.form.get('card-number')
        expiry = request.form.get('expiry')
        cvc = request.form.get('cvc')
        if not (card_number and expiry and cvc):
            return redirect(url_for('payment_page', error="All credit card fields are required"))

    # Insert into database
    conn = sqlite3.connect(DATABASE_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO payments (username, amount, city, timestamp) VALUES (?, ?, ?, ?)",
              (username, amount, city, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()

    return redirect(url_for('payment_success', username=username, amount=amount, city=city))


if __name__ == '__main__':
    init_db()
    app.run(debug=True)