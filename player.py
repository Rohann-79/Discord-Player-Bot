import discord
import yt_dlp
import os
import asyncio
from discord.ext import commands
from discord import FFmpegOpusAudio
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv('discord_token')
GUILD_ID = discord.Object(
    id=os.getenv('guild_id'))  # Update with your guild ID

# Set up the bot
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# Create voice client dictionary and song queue
voice_clients = {}
song_queues = {}

# Set up yt_dlp options for best audio format
yt_dl_options = {
    'format': 'bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio/best',
    'noplaylist': True
}

ytdl = yt_dlp.YoutubeDL(yt_dl_options)

# Set up ffmpeg options for audio filtering
ffmpeg_options = {
    'before_options':
    '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options':
    '-vn -filter:a "loudnorm=I=-16:TP=-1.5:LRA=12" -b:a 320k'  # Standard 320kbps
}


# pre bit-rate
# ffmpeg_options = {
#     'before_options':
#     '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
#     'options': '-vn -filter:a "loudnorm=I=-16:TP=-1.5:LRA=11"'
# }

# Uncomment if you want fixed volume instead of normalized
# ffmpeg_options = {
#     'before_options':
#     '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
#     'options': '-vn -filter:a "volume=0.33"'
# }

# Function to handle bot login with retry logic
async def start_bot():
  retries = 5  # Number of retries
  delay = 10  # Initial delay in seconds

  for attempt in range(retries):
    try:
      await bot.start(TOKEN)
      break  # Successfully logged in, so break out of the loop
    except discord.errors.HTTPException as e:
      if e.status == 429:  # HTTP 429 is the rate limit error
        print(f"Rate limit hit. Retrying in {delay} seconds...")
        await asyncio.sleep(delay)
        delay *= 2  # Exponential backoff
      else:
        raise  # Re-raise the exception if it's something else


# Handle bot startup and log login info
@bot.event
async def on_ready():
  print(f'Logged in as {bot.user}')

  # Sync commands only the first time
  if not hasattr(bot, 'commands_synced'):
    try:
      synced = await bot.tree.sync(guild=GUILD_ID)
      print(f"Synced {len(synced)} commands to guild {GUILD_ID.id}")
      bot.commands_synced = True
    except Exception as e:
      print(f'Error syncing commands: {e}')


@bot.tree.command(
    name="search",
    description="Search YouTube for a song and play the first result",
    guild=GUILD_ID)
async def search_song(interaction: discord.Interaction, song_title: str):
  try:
    await interaction.response.send_message(
        f"Searching for '{song_title}' on YouTube...")
    search_url = f"ytsearch:{song_title}"
    loop = asyncio.get_event_loop()
    data = await loop.run_in_executor(
        None, lambda: ytdl.extract_info(search_url, download=False))

    if 'entries' in data and len(data['entries']) > 0:
      song = data['entries'][0]
      song_url = song['url']
      title = song['title']

      if interaction.guild.id not in voice_clients or not voice_clients[
          interaction.guild.id].is_connected():
        if interaction.user.voice:
          voice_channel = interaction.user.voice.channel
          voice_client = await voice_channel.connect()
          voice_clients[interaction.guild.id] = voice_client
        else:
          await interaction.followup.send(
              "You need to join a voice channel first.")
          return
      else:
        voice_client = voice_clients[interaction.guild.id]

      if interaction.guild.id not in song_queues:
        song_queues[interaction.guild.id] = []

      # Check if song is already in the queue
      song_in_queue = any(song['url'] == queued_song['url']
                          for queued_song in song_queues[interaction.guild.id])

      # If not, add it to the queue
      if not song_in_queue:
        song_queues[interaction.guild.id].append({
            'url': song_url,
            'title': title
        })

        # Send the "Added to Queue" message only if it's added to the queue (not playing yet)
        embed = discord.Embed(title=f"Added to Queue: {title}",
                              description="Playing from YouTube",
                              color=discord.Color.blue())
        await interaction.followup.send(embed=embed)

      # If no song is currently playing, start the next song
      if not voice_client.is_playing() and not voice_client.is_paused():
        channel = interaction.channel
        await play_next_song(interaction.guild.id, voice_client, channel)

    else:
      await interaction.followup.send(f"No results found for '{song_title}'.")

  except Exception as e:
    await interaction.followup.send(f"Error: {e}")


@bot.tree.command(name="play",
                  description="Play a song from a direct YouTube link",
                  guild=GUILD_ID)
async def play_song(interaction: discord.Interaction, song_url: str):
  try:
    await interaction.response.send_message(
        f"Playing song from URL: {song_url}")

    loop = asyncio.get_event_loop()
    data = await loop.run_in_executor(
        None, lambda: ytdl.extract_info(song_url, download=False))

    title = data['title']

    # Extract the best audio URL from yt-dlp's data
    if 'formats' in data:
      audio_url = None
      for format in data['formats']:
        if format.get('acodec') != 'none' and format.get('vcodec') == 'none':
          audio_url = format['url']
          break

      if audio_url is None:
        await interaction.followup.send(
            "No audio format found for the provided URL.")
        return

      # Connect to the voice channel if not already connected
      if interaction.guild.id not in voice_clients or not voice_clients[
          interaction.guild.id].is_connected():
        if interaction.user.voice:
          voice_channel = interaction.user.voice.channel
          voice_client = await voice_channel.connect()
          voice_clients[interaction.guild.id] = voice_client
        else:
          await interaction.followup.send(
              "You need to join a voice channel first.")
          return
      else:
        voice_client = voice_clients[interaction.guild.id]

      if interaction.guild.id not in song_queues:
        song_queues[interaction.guild.id] = []

      # Prevent adding duplicates
      if title not in [
          entry['title'] for entry in song_queues[interaction.guild.id]
      ]:
        song_queues[interaction.guild.id].append({
            'url': audio_url,
            'title': title
        })

        if not voice_client.is_playing() and not voice_client.is_paused():
          # Pass the interaction channel to play_next_song
          await play_next_song(interaction.guild.id, voice_client,
                               interaction.channel)

        embed = discord.Embed(title=f"Added to Queue: {title}",
                              description="Playing from YouTube",
                              color=discord.Color.blue())
        await interaction.followup.send(embed=embed)
      else:
        await interaction.followup.send(f"'{title}' is already in the queue.")
    else:
      await interaction.followup.send(
          "Could not extract audio from the provided URL.")
  except Exception as e:
    await interaction.followup.send(f"Error: {e}")


async def play_next_song(guild_id, voice_client, channel):
  if guild_id in song_queues and len(song_queues[guild_id]) > 0:
    next_song = song_queues[guild_id].pop(0)  # Remove from queue
    song_url = next_song['url']
    title = next_song['title']

    # Start playing the song only if it's not already playing
    if not voice_client.is_playing() and not voice_client.is_paused():
      player = FFmpegOpusAudio(song_url, **ffmpeg_options)
      voice_client.play(
          player,
          after=lambda e: asyncio.run_coroutine_threadsafe(
              play_next_song(guild_id, voice_client, channel), bot.loop))

      # Send the "Now Playing" message
      embed = discord.Embed(title=f"Now Playing: {title}",
                            description="Playing from YouTube",
                            color=discord.Color.blue())
      await channel.send(embed=embed)

  else:
    await channel.send("The queue is empty.")


@bot.tree.command(
    name="skip",
    description="Skip the current song and play the next song in the queue",
    guild=GUILD_ID)
async def skip_song(interaction: discord.Interaction):
  voice_client = voice_clients.get(interaction.guild.id)

  if voice_client and voice_client.is_playing():
    # Stop the current song
    voice_client.stop()
    await interaction.response.send_message("Skipped the current song.")

    # Check if there's a next song in the queue and play it
    if interaction.guild.id in song_queues and len(
        song_queues[interaction.guild.id]) > 0:
      await play_next_song(interaction.guild.id, voice_client,
                           interaction.channel)
    else:
      await interaction.followup.send("The queue is empty.")
  else:
    await interaction.response.send_message("No song is currently playing.")


@bot.tree.command(name="pause",
                  description="Pause the current song",
                  guild=GUILD_ID)
async def pause_song(interaction: discord.Interaction):
  voice_client = voice_clients.get(interaction.guild.id)

  if voice_client and voice_client.is_playing():
    voice_client.pause()
    await interaction.response.send_message("Song paused.")
  else:
    await interaction.response.send_message("No song is currently playing.")


@bot.tree.command(name="resume",
                  description="Resume the paused song",
                  guild=GUILD_ID)
async def resume_song(interaction: discord.Interaction):
  voice_client = voice_clients.get(interaction.guild.id)

  if voice_client and voice_client.is_paused():
    voice_client.resume()
    await interaction.response.send_message("Song resumed.")
  else:
    await interaction.response.send_message("No song is currently paused.")


@bot.tree.command(
    name="stop",
    description="Stop the current song and disconnect from the voice channel",
    guild=GUILD_ID)
async def stop_song(interaction: discord.Interaction):
  voice_client = voice_clients.get(interaction.guild.id)

  if voice_client:
    voice_client.stop()
    await voice_client.disconnect()
    del voice_clients[interaction.guild.id]
    del song_queues[interaction.guild.id]
    await interaction.response.send_message(
        "Stopped the current song and disconnected.")
  else:
    await interaction.response.send_message(
        "The bot is not connected to a voice channel.")


@bot.tree.command(name="queue",
                  description="Show the current song queue",
                  guild=GUILD_ID)
async def show_queue(interaction: discord.Interaction):
  voice_client = voice_clients.get(interaction.guild.id)
  if not voice_client:
    await interaction.response.send_message(
        "The bot is not connected to a voice channel.")
    return

  if interaction.guild.id not in song_queues or len(
      song_queues[interaction.guild.id]) == 0:
    await interaction.response.send_message("The queue is empty.")
    return

  queue_list = "\n".join([
      f"{index + 1}. {song['title']}"
      for index, song in enumerate(song_queues[interaction.guild.id])
  ])
  embed = discord.Embed(title="Current Queue",
                        description=queue_list,
                        color=discord.Color.blue())
  await interaction.response.send_message(embed=embed)


# Run the bot with retry logic
asyncio.run(start_bot())
