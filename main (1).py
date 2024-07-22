import discord
from discord import app_commands
import yt_dlp
import os
import asyncio
from concurrent.futures import ThreadPoolExecutor
from moviepy.editor import AudioFileClip
import uuid
from spotdl import Spotdl

token = os.environ['token']
spotify_client_id = os.environ['clientId']
spotify_client_secret = os.environ['clientSecret']

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

MAX_FILE_SIZE_MB = 5
executor = ThreadPoolExecutor(max_workers=4)

# Initialize Spotdl with Spotify credentials
spotdl = Spotdl(
    client_id=spotify_client_id,
    client_secret=spotify_client_secret
)

def get_audio_info(url):
    ydl_opts = {
        'format': 'bestaudio/best',
        'noplaylist': True
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info_dict = ydl.extract_info(url, download=False)
        return info_dict

def download_audio(url, output_path="."):
    options = {
        'format': 'bestaudio/best',
        'outtmpl': f"{output_path}/%(title)s.%(ext)s",
    }

    with yt_dlp.YoutubeDL(options) as ydl:
        ydl.download([url])

def download_spotify_audio(url, output_path="."):
    original_cwd = os.getcwd()
    os.chdir(output_path)
    try:
        spotdl.download([url])
    finally:
        os.chdir(original_cwd)

def convert_audio(input_path, output_path):
    audio = AudioFileClip(input_path)
    audio.write_audiofile(output_path, codec='mp3')

@client.event
async def on_ready():
    await tree.sync()
    print(f'Logged in as {client.user}')

async def handle_download(interaction, url, unique_dir):
    try:
        if "spotify.com" in url:
            # Spotify download
            await asyncio.get_event_loop().run_in_executor(executor, download_spotify_audio, url, unique_dir)
        else:
            # YouTube/SoundCloud download
            info = get_audio_info(url)

            # Handle file size check more gracefully
            filesize_bytes = info.get('filesize') or info.get('filesize_approx')

            # Check if the file size is available, skip check if not
            if filesize_bytes:
                filesize_mb = filesize_bytes / (1024 * 1024)
                if filesize_mb > MAX_FILE_SIZE_MB:
                    embed = discord.Embed(
                        title="File Size Limit Exceeded",
                        description=f"Your request is {filesize_mb:.2f} MB, which exceeds the limit of {MAX_FILE_SIZE_MB} MB.",
                        color=discord.Color.red()
                    )
                    await interaction.followup.send(embed=embed)
                    return

            # Run the download and conversion in a separate thread
            await asyncio.get_event_loop().run_in_executor(executor, download_audio, url, unique_dir)

        # Check for downloaded files
        files = os.listdir(unique_dir)
        if not files:
            await interaction.followup.send('No files were downloaded.')
            return

        for file_name in files:
            file_path = os.path.join(unique_dir, file_name)
            if os.path.isfile(file_path):
                # Define the path for the converted file
                converted_file_path = os.path.splitext(file_path)[0] + '.mp3'

                # Run the conversion in a separate thread
                await asyncio.get_event_loop().run_in_executor(executor, convert_audio, file_path, converted_file_path)

                # Send the converted file to Discord
                embed = discord.Embed(
                    title="Download Complete!",
                    description="Thanks for waiting, here is your audio.",
                    color=discord.Color.purple()
                )
                embed.set_author(name=f"Requested by {interaction.user.name}", icon_url=interaction.user.avatar.url)
                embed.set_footer(text="Made by kaydavkal")
                await interaction.followup.send(embed=embed, file=discord.File(converted_file_path))

                # Clean up the original and converted files after sending them
                os.remove(file_path)
                os.remove(converted_file_path)

    except Exception as e:
        await interaction.followup.send(f'An error occurred: {e}')
    finally:
        # Clean up the unique directory
        if os.path.exists(unique_dir):
            for file in os.listdir(unique_dir):
                os.remove(os.path.join(unique_dir, file))
            os.rmdir(unique_dir)

@tree.command(name="download", description="Download audio from a given URL.")
async def download(interaction: discord.Interaction, url: str):
    embed = discord.Embed(
        title="Downloading...",
        description="Please wait while the audio is being processed.",
        color=discord.Color.purple()
    )
    embed.set_author(name=f"Requested by {interaction.user.name}", icon_url=interaction.user.avatar.url)
    embed.set_footer(text="Made by kaydavkal")
    await interaction.response.send_message(embed=embed)

    # Create a unique directory for this download
    unique_dir = f"./audio/{uuid.uuid4()}"
    os.makedirs(unique_dir)

    await handle_download(interaction, url, unique_dir)

client.run(token)