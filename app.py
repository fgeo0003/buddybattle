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
player_words = {} 

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
        # Emit an event to redirect all players to the leaderboard page
        emit("redirect_to_leaderboard", {"url": url_for("leaderboard")}, to=room)


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
        players[room] = {}
    
    # Add the player to the room with their session ID
    players[room][name] = request.sid
    
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
    
    if room in players and name in players[room]:
        del players[room][name]  # Remove the player's session ID

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

    print(f"Starting game in room: {room}")  # Debugging
    print(f"Players in room {room}: {players.get(room, {})}")  # Debugging

    # Ensure players and scores exist for the room
    if room not in players or not players[room]:
        print(f"No players in room: {room}")  # Debugging
        return

    if room not in scores:
        scores[room] = {player: 0 for player in players[room]}
    if room not in skip_counts:
        skip_counts[room] = {player: 0 for player in players[room]}

    # Initialize player_words for the room if it doesn't exist
    if room not in player_words:
        player_words[room] = {}

    # Shuffle the WORDS list to ensure unique starting words
    shuffled_words = random.sample(WORDS, len(WORDS))

    # Assign a unique word to each player
    for idx, (player, sid) in enumerate(players[room].items()):
        # Use modulo to cycle through the shuffled_words if there are more players than words
        word_index = idx % len(shuffled_words)
        current_word = shuffled_words[word_index]
        scrambled_word = scramble_word(current_word)
        player_words[room][player] = {
            "current_word": current_word,
            "scrambled_word": scrambled_word
        }

        # Emit the new word to the player using their session ID
        emit("new_word", {
            "word": scrambled_word,  # Send the scrambled word
            "player": player
        }, to=sid)

        # Debugging: Print the assigned word and scrambled word
        print(f"Player: {player}, Current Word: {current_word}, Scrambled Word: {scrambled_word}")

    print(f"Player words in room {room}: {player_words[room]}")  # Debugging


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
        emit("feedback", {"message": "You are not in this room!"}, to=request.sid)
        return

    # Ensure the player's words are initialized
    if room not in player_words or submitting_player not in player_words[room]:
        emit("feedback", {"message": "Your game data is not initialized. Please restart the game."}, to=request.sid)
        return

    # Get the player's current word
    current_word = player_words[room][submitting_player]["current_word"]
    scrambled_word = player_words[room][submitting_player]["scrambled_word"]

    # Debugging: Print the player's current word and guess
    print(f"Player: {submitting_player}, Current Word: {current_word}, Guess: {guess}")

    if guess == current_word:
        # Determine points based on the number of attempts
        attempts = data.get("attempts", 1)
        if attempts == 1:
            scores[room][submitting_player] += 5
        elif attempts == 2:
            scores[room][submitting_player] += 3
        else:
            scores[room][submitting_player] += 1

        # Emit the updated scores
        emit("update_scores", {"scores": scores[room]}, to=room)

        # Notify the player that the guess was correct
        emit("feedback", {"message": "Correct! Moving to the next word."}, to=request.sid)

        # Generate a new word for the player
        new_word = random.choice(WORDS)
        new_scrambled_word = scramble_word(new_word)
        player_words[room][submitting_player] = {
            "current_word": new_word,
            "scrambled_word": new_scrambled_word
        }

        # Emit the new word to the player using their session ID
        emit("new_word", {
            "word": new_scrambled_word,  # Send the scrambled word
            "player": submitting_player
        }, to=players[room][submitting_player])
    else:
        emit("feedback", {"message": "Wrong! Try again."}, to=request.sid)

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

        # Generate a new word for the player
        new_word = random.choice(WORDS)
        new_scrambled_word = scramble_word(new_word)
        player_words[room][submitting_player] = {
            "current_word": new_word,
            "scrambled_word": new_scrambled_word
        }

        # Emit the new word to the player
        emit("new_word", {
            "word": new_scrambled_word,
            "player": submitting_player
        }, to=player_sid)
    else:
        emit("feedback", {"message": "You have used all your skips."}, to=player_sid)

# Function to get the winning player
def get_winning_player(room):
    if room not in scores or not scores[room]:
        return None
    return max(scores[room], key=scores[room].get)  # Player with the highest score

# Function to notify the winning player
def notify_winning_player(room):
    winning_player = get_winning_player(room)
    if not winning_player:
        return

    # Send the list of ideas to the winning player
    emit("you_are_the_winner", {
        "message": "You are the winner! Select an idea to eliminate.",
        "submissions": rooms[room]["messages"]
    }, to=request.sid)

@app.route("/finalscreen")
def finalscreen():
    room = session.get("room")
    if room is None or room not in rooms:
        return redirect(url_for("home"))

    # Get the final idea
    final_idea = rooms[room]["messages"][0]["message"] if rooms[room]["messages"] else "No ideas remaining."

    return render_template("finalscreen.html", final_idea=final_idea)

@socketio.on("eliminate_idea")
def eliminate_idea(data):
    room = session.get("room")
    if room not in rooms:
        return

    winning_player = get_winning_player(room)
    submitting_player = session.get("name")

    # Ensure only the winning player can eliminate an idea
    if submitting_player != winning_player:
        emit("feedback", {"message": "Only the winning player can eliminate an idea."}, to=request.sid)
        return

    # Get the index of the idea to eliminate
    idea_index = data.get("idea_index")
    if idea_index is None or not isinstance(idea_index, int) or idea_index < 0 or idea_index >= len(rooms[room]["messages"]):
        emit("feedback", {"message": "Invalid idea selection."}, to=request.sid)
        return

    # Remove the selected idea
    eliminated_idea = rooms[room]["messages"].pop(idea_index)

    # Broadcast the eliminated idea to all players
    emit("idea_eliminated", {
        "winning_player": winning_player,
        "eliminated_idea": eliminated_idea["message"],
        "remaining_ideas": len(rooms[room]["messages"])  # Send the number of remaining ideas
    }, to=room)


def check_remaining_ideas(room):
    if room not in rooms:
        return

    remaining_ideas = len(rooms[room]["messages"])
    emit("remaining_ideas", {"remaining_ideas": remaining_ideas}, to=room)

@socketio.on("check_remaining_ideas")
def handle_check_remaining_ideas():
    room = session.get("room")
    if room not in rooms:
        return

    check_remaining_ideas(room)


@app.route("/leaderboard")
def leaderboard():
    room = session.get("room")
    if room is None or room not in rooms:
        return redirect(url_for("home"))

    # Get the scores for the room
    room_scores = scores.get(room, {})
    winning_player = get_winning_player(room)
    is_winner = session.get("name") == winning_player

    return render_template("leaderboard.html", scores=room_scores, room=room, is_winner=is_winner, rooms=rooms)


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


@socketio.on("battle_outcome")
def handle_battle_outcome():
    room = session.get("room")
    if room not in rooms:
        return

    final_url = url_for("finalscreen")
    print(f"Redirecting to: {final_url}")  # Debugging: Print the URL
    emit("redirect_to_finalscreen", {"url": final_url}, to=room)
    session.pop("room", None)


@socketio.on("continue_battle")
def handle_continue_battle():
    room = session.get("room")
    if room not in rooms:
        return

    game_url = url_for("game")  # Generate the URL for the game page
    emit("redirect_to_game", {"url": game_url}, to=room)  # Broadcast to all users in the room



if __name__ == "__main__":
    socketio.run(app, debug=True)





