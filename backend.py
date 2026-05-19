from flask import Flask, render_template, session, redirect, url_for
from flaskwebgui import FlaskUI

app = Flask(__name__)
app.secret_key = "qa567-KLu8T-ZgD45-9sdfg-1234"

@app.route('/')
def index():
    session.clear()
    return redirect(url_for('login'))


@app.route('/login')
def login():
    return render_template('login.html')
    

if __name__ == '__main__':
    FlaskUI(app=app, server="flask", width=800, height=480, port=8000).run()