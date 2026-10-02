from flask import Flask
app = Flask(__name__)

@app.route("/")
def index():
    return "OK - Flask fonctionne"

if __name__ == "__main__":
    print("DEBUT DU TEST")
    app.run(host="127.0.0.1", port=5050)
