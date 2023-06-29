import os
import time

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

def time_stamp_convert(timestamp):
    time_struct = time.localtime(timestamp)
    formatted_time = time.strftime('%Y-%m-%d %H:%M:%S', time_struct)
    return formatted_time

@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
@login_required
def index():
    portfolio = db.execute("SELECT * FROM users JOIN history ON history.user_id = users.id WHERE id = ?", session['user_id'])

    if not portfolio:
        cash = db.execute("SELECT cash FROM users WHERE id = ?", session['user_id'])
        cash = float(cash[0]['cash'])
        return render_template("index_start.html", cash=cash)

    current_prices = []
    percentages = []
    totals = [] #the final value is total cash on hand
    for stock in portfolio:
        current_price = lookup(stock['stock_symbol'])
        current_price = float(current_price['price'])
        current_prices.append(current_price)
        total_price_stock = round(current_price * stock['shares'], 2)
        totals.append(total_price_stock)
        percent = ((float(current_price) / float(stock['purchased_price'])) * 100) - 100
        percentages.append(percent)

    cash = float(portfolio[0]['cash'])
    totals.append(cash)
    total = sum(totals)


    return render_template("index.html", portfolio=portfolio, current_prices=current_prices, percentages=percentages, cash=cash, total=total)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    if request.method == "POST":
        buy = request.form.get("symbol")
        shares = request.form.get("shares")
        timestamp = int(time.time())

        if not buy:
            return apology("Must enter data", 400)

        if not shares:
            return apology("Must enter share number", 400)

        try:
            shares = float(shares)
        except ValueError:
            return apology("Must be a integer", 400)

        if shares < 0:
            return apology("Must be a positive integer", 400)


        ticker = lookup(buy)
        user_id = session['user_id']
        # this is the ticker: {'name': 'D', 'price': 51.66, 'symbol': 'D'}

        if not ticker:
            return apology("Stock Not Found", 400)

        cost = float(ticker['price']) * shares
        user_funds = db.execute("SELECT cash FROM users WHERE id = ?",session['user_id'])
        user_funds = float(user_funds[0]['cash'])

        if cost > user_funds:
            return apology("Not enough money for this purchase", 403)

        user_funds = round(user_funds - cost, 2)

        db.execute("UPDATE users SET cash = ? WHERE id = ?", user_funds, session['user_id'])

        db.execute("INSERT INTO history (stock_symbol, stock_name, purchased_price, shares, timestamp, user_id) VALUES (?, ?, ?, ?, ?, ?)", ticker['symbol'], ticker['name'], ticker['price'], shares, timestamp, user_id)

        db.execute('''
            INSERT INTO history_log
                (user_id, stock_symbol, stock_name, sell_buy, price, shares, timestamp)
            VALUES
                (?, ?, ?, ?, ?, ?, ?)
            ''',
            session['user_id'],
            ticker['symbol'],
            ticker['symbol'],
            "bought",
            float(ticker['price']),
            shares,
            time_stamp_convert(timestamp)
        )

        flash(f"Successfully purchased {shares} of {ticker['symbol']}")

        return redirect("/")
    else:
        return render_template("buy.html")




@app.route("/history")
@login_required
def history():
    history = db.execute("SELECT * FROM history_log WHERE user_id = ?", session['user_id'])

    if not history:
        flash("You have not bought or sold stock to display a history at this time")
        return redirect("/")

    return render_template("history.html", history=history)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    if request.method == "POST":
        quote = request.form.get("symbol")

        if not quote:
            return apology("Must enter a Symbol", 400)

        if not quote.isalpha():
            return apology("Must be letters", 400)

        ticker = lookup(quote)
        # this is the ticker: {'name': 'D', 'price': 51.66, 'symbol': 'D'}

        if not ticker:
            return apology("Stock Not Found", 400)

        return render_template("quoted.html", name=ticker['name'],price=ticker['price'],symbol=ticker['symbol'])
    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 400)
        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 400)
        elif request.form.get("password") != request.form.get("confirmation"):
            return apology("Passwords do not match", 400)

        # Query database for username
        row = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        # Ensure username exists and password is correct
        if len(row) >= 1:
            return apology("That username has been used", 400)

        passwordHash = generate_password_hash(request.form.get("password"))

        db.execute("INSERT INTO users (username, hash, cash) VALUES (?, ?, ?)", request.form.get("username"), passwordHash, 10000)

        flash("Registration Successful")
        # Redirect user to home page

        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("register.html")



@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    if request.method == "POST":
        ticker = request.form.get("symbol")
        shares = float(request.form.get("shares"))
        numb_shares_owned = 0
        owned = []
        timestamp = int(time.time())


        if not ticker:
            return apology("Must enter stock ticker")

        if not shares:
            return apology("Must enter share amount")

        if shares < 0:
            return apology("Must be a positive integer", 400)

        user_stocks = db.execute("SELECT history_id, stock_symbol, shares FROM users JOIN history ON history.user_id = users.id WHERE id = ? AND stock_symbol = ?", session['user_id'], ticker)

        if not user_stocks:
            return apology("You do not own any stock")
        for stock in user_stocks:
            owned.append(stock['stock_symbol'])
            numb_shares_owned += float(stock['shares'])

        if ticker not in owned:
            return apology("You do not own that stock")

        if shares > numb_shares_owned:
            return apology("You do not own that many shares")

        shares_to_sell = shares
        cash_made_from_sell = 0;
        for stock in user_stocks:
            if shares_to_sell <= 0:
                break
            current_price_share = lookup(stock['stock_symbol'])
            current_price_share = float(current_price_share['price'])
            if float(stock['shares']) <= shares_to_sell:
                shares_to_sell -= float(stock['shares'])
                cash_made_from_sell += current_price_share * float(stock['shares'])
                db.execute("DELETE FROM history WHERE history_id = ?", stock['history_id'])

                db.execute('''
                    INSERT INTO history_log
                        (user_id, stock_symbol, stock_name, sell_buy, price, shares, timestamp)
                    VALUES
                        (?, ?, ?, ?, ?, ?, ?)
                    ''',
                    session['user_id'],
                    stock['stock_symbol'],
                    stock['stock_symbol'],
                    "sold",
                    current_price_share,
                    float(stock['shares']),
                    time_stamp_convert(timestamp)
                )

            else:
                current_shares = db.execute("SELECT shares FROM history WHERE history_id = ?", stock['history_id'])
                current_shares = (float(current_shares[0]['shares'])) - shares_to_sell
                db.execute("UPDATE history SET shares = ? WHERE history_id = ?", current_shares, stock['history_id'])
                cash_made_from_sell += current_price_share * shares_to_sell

                db.execute('''
                    INSERT INTO history_log
                        (user_id, stock_symbol, stock_name, sell_buy, price, shares, timestamp)
                    VALUES
                        (?, ?, ?, ?, ?, ?, ?)
                    ''',
                    session['user_id'],
                    stock['stock_symbol'],
                    stock['stock_symbol'],
                    "sold",
                    current_price_share,
                    shares_to_sell,
                    time_stamp_convert(timestamp)
                )

                shares_to_sell = 0;

        user_cash = db.execute("SELECT cash FROM users WHERE id = ?", session['user_id'])
        user_cash = float(user_cash[0]['cash']) + cash_made_from_sell


        db.execute("UPDATE users SET cash = ? WHERE id = ?", user_cash, session['user_id'])



        flash(f"Successfully Sold {shares} of {ticker}")
        return redirect("/")
    else:
        user_info = db.execute("SELECT stock_symbol FROM users JOIN history ON history.user_id = users.id WHERE id = ?", session['user_id'])
        tickers = []
        for stock in user_info:
            tickers.append(stock['stock_symbol'])
        return render_template("sell.html", tickers=tickers)
