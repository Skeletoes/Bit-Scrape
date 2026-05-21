from flask import Flask, render_template, session, redirect, url_for, request
from flaskwebgui import FlaskUI
import sqlite3

app = Flask(__name__)
app.secret_key = "qa567-KLu8T-ZgD45-9sdfg-1234"

def databaseControl(query, data, function, table):
    # 'query' = the query that needs to be executed
    # 'data' = a list of the data that will be used for the query
    # 'function' = the what will the data be used for (e.g Add, Delete, Retrieve)
    # 'table' = what table will be effected
    dbConnection = sqlite3.connect('database.db')
    dbCursor = dbConnection.cursor()
    if function == 'add':
        if table == 'user':
            # Using try and except to handle errors and easier to diagnose the errors
            try:
                # Execute the query to add a user
                dbCursor.execute(query, (data[0], data[1], data[2], data[3]))
                # Commit to save the data
                dbConnection.commit()
            except Exception as e:
                print(f"An error occured at function=databaseControl while trying to 'add' a 'user' to the database. {e}")
    elif function == 'retrieve':
        if table == 'user':
            try:
                userData = dbCursor.execute(query, (data[0], data[1]))
                session['userID'] = userData[0]
                session['userName'] = userData[1]
                session['userEmail'] = userData[3]
                return url_for('/home')
            except Exception as e:
                print(f"An error has occured at function=databaseControl while trying to 'retrieve' data from 'user' table. {e}")
    



@app.route('/')
def index():
    session.clear()
    return redirect(url_for('login'))


@app.route('/login', methods=['POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        query = """SELECT * FROM user WHERE userName = ? AND userPassword = ?;"""
        databaseControl(query, )
    return render_template('login.html')

@app.route('/home')
def home():

    

    

if __name__ == '__main__':
    FlaskUI(app=app, server="flask", width=800, height=480, port=8000).run()