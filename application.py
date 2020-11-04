import os

from cs50 import SQL
from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""

    # query for users owned shares (updated numbers every time route is taken (lookup)), cash - user table
    # symbol, name, shares, price, total
    portfolio = []

    # returns dict with each column name as key
    inventory = db.execute("SELECT * FROM inventory WHERE user_id = :id",
                            id = session["user_id"])

    grand_total = 0

    # loop through rows in inventory and storing values in DICT so can be called in HTML after
    for row in inventory:
        shares = row["shares"]

        share_info = lookup(row["name"])

        price = share_info["price"]
        name = share_info["name"]
        total = shares * price
        portfolio.append({
            "symbol": row["name"],
            "shares": row["shares"],
            "price": usd(price),
            "name": name,
            "total": usd(total)
        })
        grand_total = grand_total + total


        # portfolio["symbol"] = inventory["name"]
        # portfolio["shares"], shares = inventory["shares"]

        # share_info = lookup(inventory["name"])

        # portfolio["price"], price = share_info["price"]
        # portfolio["name"] = share_info["name"]
        # total = price * shares
        # portfolio["total"] = total

    # get row of user
    cash_available_row = db.execute("SELECT cash FROM users WHERE id = :session_id",
                                    session_id = session["user_id"])

    # get cash of user
    cash_available = cash_available_row[0]["cash"]

    grand_total = usd(grand_total + cash_available)

    cash_available = usd(cash_available)

    # output the neccessary values to index.html to display on webpage
    # symbol, name, shares, price, TOTAL (incl CASH available last)

    return render_template("index.html", cash = cash_available, portfolio = portfolio, grand_total = grand_total)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "POST":

        if not request.form.get("symbol"):
            return apology("must provide stock name", 403)

        if not request.form.get("shares") or int(request.form.get("shares")) <= 0:
            return apology("must provide number of shares", 403)

        # store share info in DICT called share_info
        share_info = lookup(request.form.get("symbol"))

        shares = int(request.form.get("shares"))
        stock_price = share_info["price"]
        stock_name = share_info["symbol"]

        # total price of cart
        total_price = shares * stock_price

        # get row of user
        cash_available_row = db.execute("SELECT cash FROM users WHERE id = :session_id",
                                        session_id = session["user_id"])

        # get cash of user
        cash_available = cash_available_row[0]["cash"]

        # see if enough funds
        if cash_available < total_price:
            return apology("TOO POOR")

        # calculate new balance for user
        new_cash = cash_available - total_price

        db.execute("UPDATE users SET cash = :new_cash WHERE id = :session_id",
                    new_cash = new_cash,
                    session_id = session["user_id"])

        # document transaction history in "purchases" table
        db.execute("INSERT INTO purchases (user_id, stock, shares, current_price, type) VALUES (:user_id, :stock, :shares, :current_price, :type)",
                    user_id = session["user_id"],
                    stock = stock_name,
                    shares = shares,
                    current_price = stock_price,
                    type = "buy")

        # create table called 'inventory' to keep track
        # see if stock is 'in-stock'
        rows = db.execute("SELECT * FROM inventory WHERE user_id = :user_id AND name = :stock_name",
                            user_id = session["user_id"],
                            stock_name = stock_name)

        # new inventory
        if len(rows) == 0:
            db.execute("INSERT INTO inventory (user_id, shares, name) VALUES (:user_id, :shares, :stock_name)",
                        user_id = session["user_id"],
                        shares = shares,
                        stock_name = stock_name)

        # update current inventory if stock is 'in-stock'
        else:
            db.execute("UPDATE inventory SET shares=shares+:shares WHERE user_id = :user_id AND name = :stock_name",
                        shares = shares,
                        user_id = session["user_id"],
                        stock_name = stock_name)

        flash("Bought!")

        return redirect("/")
    else:
        return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    # symbol, shares, sell/buy price, transacted time
    # create list which will be used to store values from table
    history = []

    # access user's info in purchases table
    history_info = db.execute("SELECT * FROM purchases WHERE user_id = :id ORDER BY transacted DESC",
                        id = session["user_id"])

    # append into list as DICT
    for row in history_info:

        # if stock is sold, shares is negative
        if row["type"] != "buy":
            row["shares"] = -(row["shares"])

        history.append({
            "symbol": row["stock"],
            "shares": row["shares"],
            "price": usd(row["current_price"]),
            "time": row["transacted"]
        })

    return render_template("history.html", history = history)


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
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

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
    """Get stock quote."""

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # call lookup function on form input and store in DICT called symbol
        symbol = lookup(request.form.get("symbol"))
        company_name = symbol["name"]
        # format to USD
        price = usd(symbol["price"])
        symbol_name = symbol["symbol"]
        return render_template("quoted.html", company_name = company_name, price = price, symbol_name = symbol_name)

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
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

        # Ensure password was submitted again
        elif not request.form.get("confirmation"):
            return apology("must provide password again", 403)

        # Ensure passwords match
        elif request.form.get("password") != request.form.get("confirmation"):
            return apology("passwords must match", 403)

        # Generate hash of user's password
        password_hash = generate_password_hash(request.form.get("password"))

        # Storing new user into database
        db.execute("INSERT INTO users (username, hash) VALUES (:username, :hash)",
                          username=request.form.get("username"), hash=password_hash)

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    if request.method == "POST":
        if not request.form.get("symbol"):
            return apology("must provide stock name", 403)

        if not request.form.get("shares") or int(request.form.get("shares")) <= 0:
            return apology("must provide number of shares", 403)

        #update inventory and transaction tables

        symbol = request.form.get("symbol")
        sell_shares = int(request.form.get("shares"))
        rows = db.execute("SELECT name, shares FROM inventory WHERE user_id = :id AND name = :symbol",
                            id = session["user_id"],
                            symbol = symbol)

        current_shares = rows[0]["shares"]

        # if dont have stock
        if len(rows) != 1:
            return apology("Selling invalid stock")

        # if selling more shares than have
        elif current_shares < sell_shares:
            return apology("Selling more than you have")

        # everythings good - can sell shares - update tables (inventory, users cash, transactions)


        db.execute("UPDATE inventory SET shares = shares - :shares WHERE user_id = :id AND name = :symbol",
                    shares = sell_shares,
                    id = session["user_id"],
                    symbol = symbol)

        # delete stocks with 0 shares after sold
        db.execute("DELETE FROM inventory WHERE user_id = :id AND shares = 0",
                    id = session["user_id"])

        share_info = lookup(symbol)
        stock_price = share_info["price"]



        db.execute("INSERT INTO purchases (user_id, stock, shares, current_price, type) VALUES (:user_id, :stock, :shares, :current_price, :type)",
                    user_id = session["user_id"],
                    stock = symbol,
                    shares = sell_shares,
                    current_price = stock_price,
                    type = "sell")

        cash_back = float(stock_price) * float(sell_shares)

        db.execute("UPDATE users SET cash = cash + :cash_back WHERE id = :id",
                    cash_back = cash_back,
                    id = session["user_id"])

        flash("Sold!")

        return redirect("/")

    else:
        # stock sell options
        options = []

        inventory = db.execute("SELECT * FROM inventory WHERE user_id = :id",
                    id = session["user_id"])

        # create list of current inventory stock names
        for row in inventory:
            options.append(row["name"])

        return render_template("sell.html", options = options)


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
