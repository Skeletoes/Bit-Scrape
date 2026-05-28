from flask import Flask, render_template, session, redirect, url_for, request, flash
from flaskwebgui import FlaskUI
import sqlite3

app = Flask(__name__)
app.secret_key = "qa567-KLu8T-ZgD45-9sdfg-1234"

def db(query, params=()):
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute(query, params)
    conn.commit()
    results = cursor.fetchall()
    conn.close()
    return results


@app.route('/')
def index():
    session.clear()
    return redirect(url_for('login'))

# Must use 'POST' and 'GET' because 'GET' is required for the url redirection from index to login
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        # Fetch the data from the form and add it to session variables
        session['userName'] = request.form['username']
        session['userPassword'] = request.form['password']

        # Check if the user credentials are in the database
        userData = db('SELECT * FROM user WHERE userName = ? AND userPassword = ?;', (session['userName'], session['userPassword']))
        if not userData:
            flash('Credentials are incorrect')
        else:
            return redirect(url_for('home'))
    return render_template('login.html')

@app.route('/accountCreate', methods=['POST', 'GET'])
def accountCreate():
    if request.method == 'POST':
        # Get the credentials the the user input from the form
        usernameInput = request.form['username']
        passwordInput = request.form['password']
        emailInput = request.form['email']
        
        # Check the length of the username and password
        if 5 < len(usernameInput) < 20 and 5 < len(passwordInput) < 20:
            # Check if the username or email is already in the database
            userCheck = db("SELECT * FROM user WHERE userName = ? OR userEmail = ?;", (usernameInput, emailInput))
            # If the username or email is not in the database then add the user credentials
            if not userCheck:
                db("INSERT INTO user (userName, userPassword, userEmail) VALUES (?, ?, ?);", (usernameInput, passwordInput, emailInput))
                # Redirect the user to the login page so they can login with their newly created account
                return redirect(url_for('login'))
            else:
                flash('That username or email is already being used.')
        else:
            flash('The username of password is not long enough. (5 to 20 characters!!!)')

    return render_template('accountCreate.html')



@app.route('/home')
def home():
    return render_template('home.html')


if __name__ == '__main__':
    FlaskUI(app=app, server="flask", width=800, height=480, port=8000).run()