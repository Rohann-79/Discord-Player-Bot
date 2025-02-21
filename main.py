import asyncio
from keep_alive import keep_alive  # Import the function that runs the Flask server
import player  # Assuming player.py contains the bot logic


def run_flask():
  """Start the Flask server."""
  print("Running Flask server...")
  keep_alive()  # Starts the Flask server in the same thread


def run_bot():
  """Start the bot."""
  print("Running bot...")
  asyncio.run(player.runbot()
              )  # Assuming runbot() is an asynchronous function in player.py


if __name__ == "__main__":
  print("Starting Flask server first...")
  run_flask()  # Starts Flask server

  print("Starting bot after Flask server...")
  run_bot()  # Start the bot after Flask server
