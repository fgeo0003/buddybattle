from flask import Flask, render_template, request, session, redirect, url_for
from flask_socketio import join_room, leave_room, emit, send, SocketIO
import random
from string import ascii_uppercase

app = Flask(__name__)
app.config["SECRET_KEY"] = "hjhjsdahhds"
socketio = SocketIO(app)

rooms = {}
WORDS = ["python", "programming", "developer", "computer", "science", "algorithm"]
players = {}
scores = {}
current_word = {}
scrambled_word = {}
current_player_idx = {}

def generate_unique_code(length):
    while True:
        code = ""
        for _ in range(length):
            code += random.choice(ascii_uppercase)
        
        if code not in rooms:
            break
    
    return code

@app.route("/", methods=["POST", "GET"])
def home():
    session.clear()
    if request.method == "POST":
        name = request.form.get("name")
        code = request.form.get("code")
        join = request.form.get("join", False)
        create = request.form.get("create", False)

        if not name:
            return render_template("home.html", error="Please enter a name.", code=code, name=name)

        if join != False and not code:
            return render_template("home.html", error="Please enter a room code.", code=code, name=name)
        
        room = code
        if create != False:
            room = generate_unique_code(4)
            rooms[room] = {"members": 0, "messages": []}
        elif code not in rooms:
            return render_template("home.html", error="Room does not exist.", code=code, name=name)
        
        session["room"] = room
        session["name"] = name
        return redirect(url_for("room"))

    return render_template("home.html")

@app.route("/room")
def room():
    room = session.get("room")
    if room is None or session.get("name") is None or room not in rooms:
        return redirect(url_for("home"))

    return render_template("room.html", code=room, messages=rooms[room]["messages"])

@socketio.on("response")
def response(data):
    room = session.get("room")
    if room not in rooms:
        return 
    
    content = {
        "name": session.get("name"),
        "message": data["data"]
    }
    send(content, to=room)
    rooms[room]["messages"].append(content)
    print(f"{session.get('name')} suggested: {data['data']}")

@app.route("/game")
def game():
    room = session.get("room")
    if not room or room not in rooms:
        return redirect(url_for("home"))
    
    # Get the list of player names in the room
    players_in_room = rooms[room].get("players", [])

    return render_template("game.html")

@socketio.on("time_up")
def handle_time_up():
    room = session.get("room")
    if room in rooms:
        # Notify the client-side to redirect to the /game page
        emit("redirect_to_vote", {}, room=room)
        session.pop("room", None)


@socketio.on("connect")
def connect(auth):
    room = session.get("room")
    name = session.get("name")
    if not room or not name:
        return
    if room not in rooms:
        leave_room(room)
        return
    
    join_room(room)
    send({"name": name, "message": "has entered the room"}, to=room)
    
    # Add the player name to the list of players in the room
    if "players" not in rooms[room]:
        rooms[room]["players"] = []  # Initialize the players list if not already present
    rooms[room]["players"].append(name)
    rooms[room]["members"] += 1
    print(f"{name} joined room {room}")

@socketio.on("disconnect")
def disconnect():
    room = session.get("room")
    name = session.get("name")
    leave_room(room)

    if room in rooms:
        rooms[room]["members"] -= 1
        if rooms[room]["members"] <= 0:
            del rooms[room]
    
    send({"name": name, "message": "has left the room"}, to=room)
    print(f"{name} has left the room {room}")

# ======= WORD SCRAMBLE GAME LOGIC ======= #

def scramble_word(word):
    scrambled = list(word)
    random.shuffle(scrambled)
    return "".join(scrambled)

@socketio.on("start_game")
def start_game():
    room = session.get("room")
    if room not in rooms:
        return

    # Ensure players and scores exist for the room
    if room not in players:
        players[room] = rooms[room].get("players", [])  # Get players from room
    if room not in scores:
        scores[room] = {player: 0 for player in players[room]}

    current_player_idx[room] = 0
    next_turn(room)
    current_player_idx[room] = 0
    next_turn(room)

def next_turn(room):
    if room not in players or not players[room]:  
        return  

    if current_player_idx[room] >= len(players[room]):  
        current_player_idx[room] = 0  # Reset to the first player
        emit("update_scores", {"scores": scores[room]}, to=room)

    current_word[room] = random.choice(WORDS)
    scrambled_word[room] = scramble_word(current_word[room])

    emit("new_word", {
        "player": players[room][current_player_idx[room]],
        "word": scrambled_word[room]
    }, to=room)

@socketio.on("submit_guess")
def check_answer(data):
    room = session.get("room")
    if room not in rooms:
        return
    guess = data["guess"].strip()
    current_player = players[room][current_player_idx[room]]

    if guess == current_word[room]:
        scores[room][current_player] += 5
        emit("feedback", {"message": "Correct! Moving to next turn."}, to=room)
        current_player_idx[room] += 1
        next_turn(room)
    else:
        emit("feedback", {"message": "Wrong! Try again."}, to=room)

if __name__ == "__main__":
    socketio.run(app, debug=True)
