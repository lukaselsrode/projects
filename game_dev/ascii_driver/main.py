from flask import Flask,render_template,request,jsonify
import subprocess

app=Flask(__name__,template_folder='./templates')
app.config['TESTING'] = True
app.config['DEBUG'] = True


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/game')
def game():
    proc=subprocess.Popen(['python3','game.py'],stdin=subprocess.PIPE,stdout=subprocess.PIPE)
    while True:
        out=proc.stdout.read().decode()
        if not out: break
        return render_template('game.html',output=out)




















































@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/leaderboard')
def leaderboard():
    return render_template('scores.html')



if __name__ == '__main__':
    app.run(debug=True)
