from flask import Flask, render_template, request, session, redirect, url_for
from flask_socketio import join_room, leave_room, send, emit, SocketIO
import random
from string import ascii_uppercase

app = Flask(__name__)
app.config["SECRET_KEY"] = "hjhjsdahhds"
socketio = SocketIO(app)

rooms = {}

def generate_unique_code(length):
    while True:
        code = "".join(random.choice(ascii_uppercase) for _ in range(length))
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

        if join and not code:
            return render_template("home.html", error="Please enter a room code.", code=code, name=name)

        room = code
        if create:
            room = generate_unique_code(4)
            rooms[room] = {"members": 0, "activities": []}
        elif code not in rooms:
            return render_template("home.html", error="Room does not exist.", code=code, name=name)

        session["room"] = room
        session["name"] = name
        return redirect(url_for("room"))

    return render_template("home.html")

@app.route("/room")
def room():
    room = session.get("room")
    if not room or session.get("name") is None or room not in rooms:
        return redirect(url_for("home"))

    return render_template("room.html", code=room)

@app.route("/vote")
def vote():
    room = session.get("room")
    if not room or room not in rooms:
        return redirect(url_for("home"))

    return render_template("vote.html")

@socketio.on("activity")
def handle_activity(data):
    room = session.get("room")
    if room not in rooms:
        return 

    activity = data["data"]
    rooms[room]["activities"].append(activity)

    emit("activity", {"message": activity}, to=room)
    print(f"Activity submitted: {activity}")

@socketio.on("time_up")
def handle_time_up():
    room = session.get("room")
    if room in rooms:
        emit("redirect_to_vote", {}, to=room)

@socketio.on("request_activities")
def send_activities():
    room = session.get("room")
    if room in rooms:
        emit("load_activities", {"activities": rooms[room]["activities"]})

@socketio.on("connect")
def connect():
    room = session.get("room")
    name = session.get("name")
    if not room or not name:
        return
    if room not in rooms:
        leave_room(room)
        return
    
    join_room(room)
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

    print(f"{name} has left the room {room}")

if __name__ == "__main__":
    socketio.run(app, debug=True)
