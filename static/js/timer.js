document.addEventListener("DOMContentLoaded", function () {
    let timeLeft = 10;  // Starting time
    const totalTime = 10; // Total countdown time
    const timerText = document.getElementById("timer-text");
    const countdownCircle = document.querySelector(".countdown-circle");

    function updateTimer() {
        timerText.textContent = timeLeft;  // Update the text inside the circle

        // Calculate the stroke-dashoffset based on time left
        let circumference = 2 * Math.PI * 45; // 2πr (r=45)
        let progress = (timeLeft / totalTime) * circumference;
        countdownCircle.style.strokeDashoffset = circumference - progress;

        if (timeLeft === 0) {
            socketio.emit("time_up");  // Notify server that time is up
        } else {
            timeLeft--;
            setTimeout(updateTimer, 1000); // Update every second
        }
    }

    updateTimer(); // Start the timer
});
