from flask import Flask, request, jsonify, send_from_directory, render_template
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
import jwt, datetime, os

app = Flask(__name__, template_folder='templates')
CORS(app)

app.config['SECRET_KEY'] = 'green_trust_secret_123'

# In-memory database
users = {
    "Philbert": {
        "password": generate_password_hash("123"),
        "email": "admin@greentrust.com"
    }
}

# -------------------------------
# Auth Routes
# -------------------------------
@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')

    if username in users and check_password_hash(users[username]['password'], password):
        token = jwt.encode({
            'username': username, 
            'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=24)
        }, app.config['SECRET_KEY'], algorithm="HS256")
        return jsonify({'access_token': token})
    
    return jsonify({'message': 'Invalid credentials'}), 401

# -------------------------------
# Prediction Route
# -------------------------------
@app.route('/predict_single', methods=['POST'])
def predict_single():
    # In a real app, you'd use @token_required here
    data = request.get_json()
    
    # Simple logic based on your image (Growth/Stability)
    score = float(data.get('credit_score', 0))
    income = float(data.get('annual_income', 0))
    
    # Normalize probability
    prob = (score / 850) * 0.7 + (min(income, 100000) / 100000) * 0.3
    prediction = 1 if prob > 0.6 else 0
    
    return jsonify({
        'prediction': prediction,
        'probability': round(prob, 4)
    })

# -------------------------------
# Static Files & UI
# -------------------------------
@app.route("/")
def home():
    return render_template("hey.html")

@app.route('/pic.jpeg')
def send_bg():
    return send_from_directory(os.getcwd(), 'pic.jpeg')

if __name__ == "__main__":
    app.run(debug=True, port=8080)