from flask import Flask, render_template, url_for, flash, jsonify, request, g, session, redirect
from bookapp import app, Base, engine, dbSession, bcrypt
from bookapp.forms import RegistrationForm, LoginForm
from bookapp.models import User, Review, Book
import requests
import datetime
from flask_paginate import Pagination, get_page_args

# 2 - generate database schema
Base.metadata.create_all(engine)

@app.route("/")
@app.route("/home")
def home():
    reg_form = RegistrationForm()
    login_form = LoginForm()
    return render_template('index.html', reg_form=reg_form, login_form=login_form)

@app.route('/register', methods=['post', 'get'])
def register():
    message = None
    reg_form = RegistrationForm()
    login_form = LoginForm()

    if request.method == 'GET':
        return render_template('register.html',  reg_form=reg_form, login_form=login_form)

    if request.method == 'POST':
        if reg_form.validate_on_submit():
            hashed_password = bcrypt.generate_password_hash(reg_form.password.data).decode('utf-8')
            dbSession.execute(
                "INSERT INTO users (username, email, password) VALUES (:username, :email, :password)",
                {"username": reg_form.username.data, "email":  reg_form.email.data, "password": hashed_password}
            )
            dbSession.commit()
            dbSession.close()
            return jsonify({'success': 'Registration Successful'})
    return jsonify({'errors': reg_form.errors})

@app.route("/login", methods=['post', 'get'])
def login():
    login_form = LoginForm()
    reg_form = RegistrationForm()

    if request.method == 'GET':
        return render_template('login.html', login_form=login_form,  reg_form=reg_form)

    if request.method == 'POST':
        user = dbSession.execute(
            "SELECT * FROM users WHERE email = :email",
            {"email": login_form.email.data}
        ).fetchone()
        dbSession.close()
        if login_form.validate_on_submit():
            session.clear()
            session['user_id'] = user['id'] #add user id on session
            return jsonify({'success': 'Login Successful'})
    return jsonify({'errors': login_form.errors})

@app.before_request
def load_logged_in_user():
    user_id = session.get('user_id')
    if user_id is None:
        g.user = None
    else:
        g.user = dbSession.execute(
            "SELECT * FROM users WHERE id = :id",
            { "id": user_id }
        ).fetchone()
        dbSession.close()

@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return response

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))

@app.route("/search", methods=['get', 'post'])
def search():
    if request.method == 'POST':
        text = request.form.get("searchText")
        print(text)
        result = dbSession.execute(
            "SELECT * FROM books WHERE (LOWER(isbn) LIKE LOWER(:text)) OR (LOWER(title) LIKE LOWER(:text)) OR (author LIKE LOWER(:text)) LIMIT 10",
            { "text": '%' + text + '%'} 
        ).fetchall()
        dbSession.close()
        data = []
        for row in result:
            data.append(dict(row))
            print(data)
        return jsonify({ 'data': data })
# book route with pagination
PER_PAGE = 20

@app.route("/book/<isbn>", methods=['get', 'post'])
def book(isbn):

    login_form = LoginForm()
    reg_form = RegistrationForm()

    if request.method == 'GET':

        voted = None
        userId = session.get('user_id')
        reviews = None

        book = dbSession.execute(
            "SELECT * FROM books WHERE isbn = :isbn",
            { "isbn": isbn }
        ).fetchone()

        user = dbSession.execute(
            "SELECT * FROM reviews WHERE book_id = :book_id AND user_id = :user_id",
            { "book_id": book['id'], "user_id": userId }
        ).fetchone()

        if user is not None:
            voted=bool(user)

        if book is not None:

            page, per_page, offset = get_page_args(page_parameter='page', per_page_parameter='per_page')

            print ("page = {} ".format(page))
            print ("per_page = {} ".format(per_page))
            print ("offset = {} ".format(offset))

            pagination_reviews = dbSession.execute(
                "SELECT u.username, r.* FROM users AS u JOIN reviews AS r ON u.id = r.user_id WHERE book_id = :book_id LIMIT :items_per_page OFFSET (:page * :items_per_page)",
                { "book_id": book['id'], "items_per_page": per_page, "page": page - 1 }
            ).fetchall()

            print ("pagination_reviews = {} ".format(pagination_reviews))

            totalReviewRows =  dbSession.execute(
                "SELECT COUNT(*) FROM reviews WHERE book_id = :book_id",
                { "book_id": book['id'] }
            ).fetchone()[0]

            print ("totalReviewRows = {} ".format(totalReviewRows))

            reviewsData = []

            pagination = Pagination(page=page, per_page=per_page, total=totalReviewRows, css_framework='bootstrap4')

            for row in pagination_reviews:
                reviewsData.append(dict(row))
        
        dbSession.close()
        
        return render_template(
            "book.html",
            book=book,
            reviews=reviewsData,
            voted=voted,
            login_form=login_form, 
            reg_form=reg_form,
            page=page,
            per_page=per_page,
            pagination=pagination,
        )
                                         
    # if request.method == 'POST':
    #     rating = request.form.get("rating")
    #     content = request.form.get("content")
    #     book_id = request.form.get("book-id")
    #     user_id = session.get('user_id')
    #     date_posted = datetime.datetime.now()
    #     dbSession.execute(
    #         "INSERT INTO users (username, email, password) VALUES (:username, :email, :password)",
    #         {"username": reg_form.username.data, "email":  reg_form.email.data, "password": hashed_password}
    #     )
    #     dbSession.commit()
    #     return jsonify({ 'data': 'a'})

@app.route("/addreview", methods=['get', 'post'])
def addreview():
    if request.method == 'POST':
        req_data = request.get_json()
        rate = req_data['rate']
        text = req_data['text']
        userId = req_data['userId']
        bookId = req_data['bookId']
        dt = datetime.datetime.now()
        dbSession.execute(
            "INSERT INTO reviews (content, date_posted, user_id, book_id, rating) VALUES (:content, :date_posted, :user_id, :book_id, :rating)",
            {"content": text, "date_posted":  dt, "user_id": userId, "book_id": bookId, "rating": rate }
        )
        dbSession.commit()
        # LOGIC: one user can only review 1x on a book, so if we can query the book here,
        # provided with user id and book id, we retrieve the users' review
        reviewByUser = dbSession.execute(
            "SELECT u.username, r.* FROM users AS u JOIN reviews AS r ON u.id = r.user_id WHERE book_id = :book_id AND user_id = :user_id",
            { "book_id": bookId, "user_id": userId }
        ).fetchone()
        
        dbSession.close()
        
        return jsonify(dict(reviewByUser))

# @app.route("/api/<int:isbn>")
# def flight(isbn):
#     # Make sure flight exists.
#     res = requests.get(
#         "https://www.goodreads.com/book/review_counts.json",
#         params={ "key": "KEY", "isbns": isbn }
#     )
#     book = db.execute("SELECT * FROM books WHERE isbn = :isbn", {"isbn": isbn}).fetchone()
#     if book is None:
#         return render_template("book.html", message="No such flight.")

#     # Get all passengers.
#     passengers = db.execute("SELECT name FROM passengers WHERE flight_id = :flight_id",
#                             {"flight_id": flight_id}).fetchall()
#     return render_template("flight.html", flight=flight, passengers=passengers)


if __name__ == '__main__':
    app.run(debug=True)