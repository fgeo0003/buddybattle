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
        max_players = request.form.get("max_players", type=int)

        if not name:
            return render_template("home.html", error="Please enter a name.", code=code, name=name)

        if join != False and not code:
            return render_template("home.html", error="Please enter a room code.", code=code, name=name)
        
        room = code
        if create != False:
            if not max_players or max_players < 2:
                return render_template("home.html", error="Please enter a valid number of players (2-10).", code=code, name=name)
            room = generate_unique_code(4)
            rooms[room] = {
                "members": 0,
                "messages": [],
                "max_players": max_players,
                "users_who_submitted": [],
                "submission_count": 0,  # Track number of submissions
            }
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

    return render_template("room.html", code=room, messages=rooms[room]["messages"], max_players=rooms[room]["max_players"], current_players=rooms[room]["members"])

@app.route("/game")
def game():
    room = session.get("room")
    if room is None or session.get("name") is None or room not in rooms:
        return redirect(url_for("home"))

    return render_template("game.html", messages=rooms[room]["messages"])


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
    
    # Initialize players dictionary for the room if it doesn't exist
    if room not in players:
        players[room] = []
    
    # Add the player to the room if they're not already in the list
    if name not in players[room]:
        players[room].append(name)
    
    # Update room members count
    rooms[room]["members"] += 1
    
    # Send a message to the room that a new player has joined
    send({"name": name, "message": "has entered the room"}, to=room)
    
    # Emit player count update to the room
    emit("player_count_update", {
        "current_players": rooms[room]["members"],
        "max_players": rooms[room]["max_players"]
    }, to=room)
    
    print(f"{name} joined room {room}")
    print(f"Players in room {room}: {players[room]}")  # Debugging: Print players in the room

@socketio.on("disconnect")
def disconnect():
    room = session.get("room")
    name = session.get("name")
    leave_room(room)

    if room in rooms:
        rooms[room]["members"] -= 1
        if rooms[room]["members"] <= 0:
            del rooms[room]
        else:
            emit("player_count_update", {"current_players": rooms[room]["members"], "max_players": rooms[room]["max_players"]}, to=room)
    
    send({"name": name, "message": "has left the room"}, to=room)
    print(f"{name} has left the room {room}")



# ======= WORD MIX GAME LOGIC ======= #
# Add a dictionary to track the number of skips used by each player
skip_counts = {}

@socketio.on("start_game")
def start_game():
    room = session.get("room")
    if room not in rooms:
        return

    # Ensure players and scores exist for the room
    if room not in players or not players[room]:
        return

    if room not in scores:
        scores[room] = {player: 0 for player in players[room]}
    if room not in skip_counts:
        skip_counts[room] = {player: 0 for player in players[room]}
    
    # Generate the first word and emit it to the room
    current_word[room] = random.choice(WORDS)
    scrambled_word[room] = scramble_word(current_word[room])
    emit("new_word", {"word": scrambled_word[room]}, to=room)


def scramble_word(word):
    scrambled = list(word)
    random.shuffle(scrambled)
    return "".join(scrambled)


@socketio.on("submit_guess")
def check_answer(data):
    room = session.get("room")
    if room not in rooms:
        return

    guess = data["guess"].strip()
    submitting_player = session.get("name")  # Get the name of the player submitting the guess

    # Ensure the submitting player is in the room
    if submitting_player not in players[room]:
        emit("feedback", {"message": "You are not in this room!"}, to=room)
        return

    if guess == current_word[room]:
        # Determine points based on the number of attempts
        attempts = data.get("attempts", 1)
        if attempts == 1:
            scores[room][submitting_player] += 5  # Update the submitting player's score
        elif attempts == 2:
            scores[room][submitting_player] += 3
        else:
            scores[room][submitting_player] += 1

        # Emit the updated scores
        emit("update_scores", {"scores": scores[room]}, to=room)

        # Notify the player that the guess was correct
        emit("feedback", {"message": f"Correct! {submitting_player} earns points."}, to=room)

        # Generate a new word and emit it to the room
        current_word[room] = random.choice(WORDS)
        scrambled_word[room] = scramble_word(current_word[room])
        emit("new_word", {"word": scrambled_word[room]}, to=room)
    else:
        emit("feedback", {"message": "Wrong! Try again."}, to=room)

@socketio.on("skip_word")
def skip_word():
    room = session.get("room")
    if room not in rooms:
        return

    submitting_player = session.get("name")  # Get the name of the player submitting the skip request
    player_sid = request.sid  # Get the session ID of the player

    # Ensure the submitting player is in the room
    if submitting_player not in players[room]:
        emit("feedback", {"message": "You are not in this room!"}, to=player_sid)
        return

    # Initialize skip_counts for the room if it doesn't exist
    if room not in skip_counts:
        skip_counts[room] = {player: 0 for player in players[room]}

    # Check if the player has used fewer than 2 skips
    if skip_counts[room][submitting_player] < 2:
        skip_counts[room][submitting_player] += 1  # Increment the player's skip count
        emit("feedback", {"message": f"Word skipped. You have {2 - skip_counts[room][submitting_player]} skips left."}, to=player_sid)

        # Generate a new word and emit it only to the player who skipped
        current_word[room] = random.choice(WORDS)
        scrambled_word[room] = scramble_word(current_word[room])
        emit("new_word", {"word": scrambled_word[room]}, to=player_sid)
    else:
        emit("feedback", {"message": "You have used all your skips."}, to=player_sid)


### FIONA - CHAT ROOM ###

@socketio.on("message")
def handle_message(data):
    room = session.get("room")
    name = session.get("name")
    if room not in rooms:
        return 
    
    # Check if the user has already submitted a message
    if name in rooms[room]["users_who_submitted"]:
        return  # User has already submitted

    # Store the message
    content = {
        "name": name,
        "message": data["data"]
    }
    rooms[room]["messages"].append(content)
    rooms[room]["users_who_submitted"].append(name)
    rooms[room]["submission_count"] += 1

    # Broadcast the message to the room
    send(content, to=room)

    # Check if all users have submitted
    if rooms[room]["submission_count"] >= rooms[room]["max_players"]:
        # Emit an event to display all submissions
        emit("all_submissions_received", {"submissions": rooms[room]["messages"]}, to=room)

@socketio.on("start_battle")
def handle_start_battle():
    room = session.get("room")
    if room not in rooms:
        return

    game_url = url_for("game")
    print(f"Redirecting to: {game_url}")  # Debugging: Print the URL
    emit("redirect_to_game", {"url": game_url}, to=room)
    session.pop("room", None)


if __name__ == "__main__":
    socketio.run(app, debug=True)


    


