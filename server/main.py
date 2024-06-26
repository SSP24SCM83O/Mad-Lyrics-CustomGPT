from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from typing import Dict, List
import openai
import base64
import json
import re
import random
from io import BytesIO
import asyncio

from suno import SongsGen
from dotenv import load_dotenv
import os

from starlette.middleware.cors import CORSMiddleware

load_dotenv()

app = FastAPI()

origins = [
    "http://localhost:3000",
    "http://localhost:3000/*",
    # "http://localhost",
    # "http://localhost:8080",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SUNO_COOKIE = os.getenv("SUNO_COOKIE")



openai.api_key = os.getenv("OPEN_AI_API_KEY")

class Name(BaseModel):
    firstName: str = "Sai"
    lastName: str = "Ram"
# manages the connection across mukt clients and sate of ws
class ConnectionManager:
    # initializes ws and adds to active connections inside of a dictionary
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.ready_players: Dict[str, bool] = {}
        self.player_inputs: Dict[str, List[List[str]]] = {}
        self.currentLyrics: str = ""
        self.num_inputs = 0
        self.order_players_by_arrival: List[str] = []
        self.player_genres: Dict[str, str] = {}
        self.player_emotions: Dict[str, str] = {}
        self.player_topics: Dict[str, str] = {}
        self.selected_topic: str = ""


    # establish connection btwn a client and ws. waits for ws to start and adds accepted client to active connections
    async def connect(self, websocket: WebSocket, client_id: str):
        await websocket.accept()
        self.active_connections[client_id] = websocket
        self.ready_players[client_id] = False # literally spaghetti code
        self.player_inputs[client_id] = [] # literally spaghetti code
        self.order_players_by_arrival.append(client_id)
        self.player_genres[client_id] = "" # literally spaghetti code
        self.player_emotions[client_id] = "" # literally spaghetti code
        self.player_topics[client_id] = "" # literally spaghetti code

        print(self.active_connections)
        # send the new connections
        obj = {
            "event": "connection",
            "players": self.order_players_by_arrival
        }
        await self.broadcast(obj)
        
    # disconnects client from ws
    async def disconnect(self, client_id: str):
        del self.active_connections[client_id]
        del self.ready_players[client_id]
        del self.player_inputs[client_id]
        del self.player_genres[client_id]
        del self.player_emotions[client_id]
        del self.player_topics[client_id]

        print(self.active_connections)
        # remove player order
        self.order_players_by_arrival = [s for s in self.order_players_by_arrival if s != client_id]
        obj = {
            "event": "connection",
            "players": self.order_players_by_arrival
        }
        await self.broadcast(obj)
    #  converts music into binary which it then sends as bytes
    async def send_personal_message(self, data: dict, websocket: WebSocket):
        await websocket.send_json(data)
    # shows music to all clients with active connections to the ws
    async def broadcast(self, data: dict):
        for connection in self.active_connections.values():
            await connection.send_json(data)


manager = ConnectionManager()


@app.get("/helloworld")
# function handles requests that go to path "/" with the "get" operation
async def root():
    return {"message": "Hello World"}

@app.get("/items/{item_id}")
async def read_item(item_id):
    return {"item_id": item_id}

@app.post("/name")
async def create_name(name:Name):
    # f embeds code into a string
    return {f"Hello, {name.firstName} {name.lastName}"}

# websocket
@app.websocket("/ws")
# default state of client is none
async def websocket_endpoint(websocket: WebSocket, client_id: str | None = None):
    if client_id is None:
        client_id = websocket.query_params.get("client_id")

    if client_id is None:
        await websocket.close(code=4001)
        return
    # save this client into server memory
    await manager.connect(websocket, client_id)      
    try:
        while True:
            data = await websocket.receive_json()
            event = data["event"]
            if event == "generate":
                lyrics = data["lyrics"]
                genre = data["genre"]
                # create var that calls the function to generate a song using the Suno function "songGen" with the suno api key
                # get_songs_custom is a function under suno with the lyrics and genre passed through the combined user prompted genre and gpt generated lyrics
                output = GenerateSong.get_songs_custom(lyrics, genre)
                # returns a link from the "song url" element inside of the output item in dictionary, stored in link. The first element in the array
                link = output['song_urls'][0]
                # gets the mp3 associated with each link and sets streaming in websocket to true, meaning that data is sent in chunks
                audio = GenerateSong.get_mp3(link, stream=True)
                for chunk in audio:
                    if chunk:
                        # translates binary to base64 string
                        b64 = base64.b64encode(chunk)
                        # decodes the b.64 binary obj into a string
                        utf = b64.decode('utf-8')
                        # creates a dict obj that stores the event as an audio chunk and sets the audio data to utf format
                        obj = {
                            "event": "audio",
                            "audio_data": utf
                        }
                        # waits for broadcasting to run
                        await manager.broadcast(obj)

            elif event == "lyrics":
                print("lyrics")
                # lyrics = lyrics_data["lyrics"][0]
                # await websocket.send_json({
                #     "event": "lyrics",
                #     "data": lyrics
                # })
            elif event == "sample_song":
                print("Getting sample song manually")
                path_to_song = './output/2 .mp3'
                with open(path_to_song, 'rb') as mp3_file:
                    while True:
                        # reading data in chunks of 4kb
                        chunk = mp3_file.read(512)
                        print("chunk", flush=True)
                        if not chunk:
                            break
                        #translates bits and bytes into text
                        b64 = base64.b64encode(chunk)
                        # translates the text into a universally understandable language for diff computers
                        utf = b64.decode('utf-8')
                        obj = {
                            "event": "audio",
                            "audio_data": utf
                        }
                        await manager.broadcast(obj)
            
            elif event == "start":
                print("Starting Mad Lyrics")
                # call the api
                # make everyone wait
                obj = {
                    "event": "phase_change",
                    "data": "lobby_wait"
                }
                await manager.broadcast(obj)

                # get prompt from GPT
                lyrics = await get_lyrics()

                # now move all players
                obj = {
                    "event": "phase_change",
                    "data": "input"
                }
                await manager.broadcast(lyrics)
                # This should bring players from the lobby to the input screen
                await manager.broadcast(obj)
            elif event == "finished":
                # parse out the event data to get which player finished
                # expect: {"event": "finished", "id": string, "libs": string[][]}
                id = data["id"]
                libs = data["libs"]
                manager.ready_players[id] = True
                manager.player_inputs[id] = libs
                # if all players are ready, move them to the waiting screen
                all_ready = all(value for value in manager.ready_players.values())
                if all_ready:
                    # bring all players to the moving screen
                    print("READY TO GENERATE")
                    print(manager.player_inputs)
                    # randomly select from inputs
                    # flatten each player's input for ease of parsing
                    all_flattened_inputs = []
                    for player in manager.player_inputs:
                        flattened_inputs = [item for sublist in manager.player_inputs[player] for item in sublist]
                        all_flattened_inputs.append(flattened_inputs)
                    # choose random choices
                    # iterate through each input
                    print(manager.num_inputs)
                    print(all_flattened_inputs)
                    combined_list = []
                    for inputIndex in range(0, manager.num_inputs):
                        num_players = len(manager.player_inputs.keys())
                        # check if there is any choice that has no inputs
                        # Initialize a list to store the results for each index
                        curr_list = []
                        # Loop through each index from 0 to 16
                        for i in range(0, num_players):
                            # Check if any player has a non-empty string at the current index
                            if len(all_flattened_inputs[i][inputIndex]) > 0:
                                curr_list.append(all_flattened_inputs[i][inputIndex])
                        if(len(curr_list) > 0):
                            # choose a random one
                            randomInt = generate_random_number(len(curr_list))
                            selectedPlayerInputs = curr_list[randomInt]
                            combined_list.append(selectedPlayerInputs)
                        else:
                            # TODO: replace this
                            combined_list.append('dog')
                
                    # replace prompt with end_inputs
                    print(combined_list)
                    pattern = r'\{.*?\}'
                    # turn the json structure into just a plain string
                    output = ""
                    # print(manager.currentLyrics)
                    for section in json.loads(manager.currentLyrics):
                        output += f"{section['part']}:\n"
                        output += "\n".join(section["lyrics"]) + "\n\n"
                    print(output)
                    replaced_lyrics = output
                    current_input_index = 0
                    # While there are matches and the current_input_index is less than the length of combined_list
                    while re.search(pattern, replaced_lyrics) and current_input_index < len(combined_list):
                        # Replace the first instance
                        replaced_lyrics = re.sub(pattern, combined_list[current_input_index], replaced_lyrics, count=1)
                        current_input_index += 1

                    print(replaced_lyrics)

                    # call Suno
                    # choose a random genre
                    selected_genre = get_random_non_empty_entry(manager.player_genres)
                    if selected_genre is None:
                        selected_genre = "Pop"

                    selected_emotion = get_random_non_empty_entry(manager.player_emotions)
                    if selected_emotion is None:
                        selected_emotion = "Upbeat"

                    genre = selected_emotion + " " + selected_genre
                    # genre = data["genre"]
                    # create var that calls the function to generate a song using the Suno function "songGen" with the suno api key
                    # get_songs_custom is a function under suno with the lyrics and genre passed through the combined user prompted genre and gpt generated lyrics
                    print("LYRICS: " + replaced_lyrics)
                    print("GENRE: " + genre)
                    GenerateSong = SongsGen(SUNO_COOKIE)
                    print(GenerateSong.get_limit_left())
                    output = GenerateSong.get_songs_custom(replaced_lyrics, genre)
                    
                    obj = {
                        "event": "phase_change",
                        "data": "song"
                    }
                    
                    await manager.broadcast(obj)
                    await asyncio.sleep(1)
                    # returns a link from the "song url" element inside of the output item in dictionary, stored in link. The first element in the array
                    link = output['song_urls'][0]
                    print("SUNO OUTPUT:")
                    print(output)
                    title = output['song_name']
                    lyrics = output['lyric']
                    # gets the mp3 associated with each link and sets streaming in websocket to true, meaning that data is sent in chunks
                    audio = GenerateSong.get_mp3(link, stream=True)
                    buffer = BytesIO()
                    desired_chunk_size = 48000
                    async def process_and_send_large_chunk():
                        # Check if the buffer has enough data to process
                        # You can adjust the size check as needed
                        if buffer.getbuffer().nbytes >= desired_chunk_size:
                            # Reset buffer position to the start
                            buffer.seek(0)

                            # Read the data from the buffer
                            large_chunk = buffer.read()

                            # Translate binary to base64 string
                            b64 = base64.b64encode(large_chunk)

                            # Decode the base64 binary object into a string
                            utf = b64.decode('utf-8')

                            # Create a dict object that stores the event as an audio chunk and sets the audio data to utf format
                            obj = {
                                "event": "audio",
                                "audio_data": utf,
                                "title": title,
                                "lyrics": lyrics,
                                "genre": genre,
                                "topic": manager.selected_topic
                            }
                            
                            # Wait for broadcasting to run
                            await manager.broadcast(obj)
                            
                            # Clear the buffer after sending
                            buffer.seek(0)
                            buffer.truncate()
                    for chunk in audio:
                        if chunk:
                            # translates binary to base64 string
                            buffer.write(chunk)
                            
                            await process_and_send_large_chunk()
                    
                    

                    # # TODO: Remove sample song
                    # print("Getting sample song")
                    # path_to_song = './output/2 .mp3'
                    # with open(path_to_song, 'rb') as mp3_file:
                    #     while True:
                    #         # reading data in chunks of 4kb
                    #         chunk = mp3_file.read(48000)
                    #         print("chunk", flush=True)
                    #         if not chunk:
                    #             break
                    #         b64 = base64.b64encode(chunk)
                    #         utf = b64.decode('utf-8')
                    #         obj = {
                    #             "event": "audio",
                    #             "audio_data": utf
                    #         }
                    #         await manager.broadcast(obj)

            elif event == "genre":
                # update genre in backend
                id = data["id"]
                genre = data["genre"]
                manager.player_genres[id] = genre

            elif event == "emotion":
                # update emotion in backend
                id = data["id"]
                emotion = data["emotion"]
                manager.player_emotions[id] = emotion

            elif event == "topic":
                # update emotion in backend
                id = data["id"]
                topic = data["topic"]
                manager.player_topics[id] = topic
                
    except WebSocketDisconnect:
        print("Disconnecting...")
        await manager.disconnect(client_id)

# chatgpt 
@app.get("/lyricstemplate")
async def get_lyrics():
    topic = get_random_non_empty_entry(manager.player_topics)
    if topic is None:
        topic = ""
    else:
        manager.selected_topic = topic
        topic = "about " + topic
    # call chatgpt
    prompt = [
        {"role": "system", "content": "You are a intelligent assistant."},

        {"role": "user", "content": """
You will generate a mad-libs puzzle and output the mad-libs in a JSON schema. Here is an example of the JSON schema I want:
[
  {
    "part": "Verse",
    "lyrics": [
      "The wind in the night, it whispers so {adjective},",
      "Carrying tales from the {noun} so {adjective}.",
      "My {noun} in my hand, ancient and {adjective},",
      "Across the endless fields, our shadows {verb}."
    ]
  },
  {
    "part": "Chorus",
    "lyrics": [
      "With every step, I grow {adjective},",
      "In a realm where {noun} softly {verb}.",
      "But by your {noun}, I sail my {noun},",
      "And in your voice, the {noun} I've long {verb}."
    ]
  },
  {
    "part": "Bridge",
    "lyrics": [
      "Under the gaze of the {noun}, we {verb},",
      "To the rhythm that makes our hearts {verb},",
      "Side by side, we {verb} and {verb},",
      "In this {noun} dream, where hope brightly {verb}."
    ]
  },
  {
    "part": "Outro",
    "lyrics": [
      "Here's to the {noun}, the light, and the {noun},",
      "On this path, we're forever {adjective}.",
      "From dawn to dusk, under the sky's {noun},",
      "Together, into the unknown we {verb}."
    ]
  }
]
Create lyrics """ + topic + """ following the same JSON schema. The lyrics themselves should be quite different from what I put, as well as the mad libs. My example only applies to the JSON format. The mad libs should be annotated by the proper type of speech ie. {noun}. The valid parts of speech are: noun, adjective, verb, and adverb. 

Make four verses: Verse, Chorus, Bridge,  and Outro. Each verses will have 4 lines.
Never have two mad-libs next to each other in the same line. For example, {adjective} {noun} is invalid.

Have only 1 mad lib per line. There must be 1 mad-lib per line.
"""}
    ]
    chat = openai.chat.completions.create( 
            model="gpt-4-turbo-preview", messages=prompt
        )
    
    reply = chat.choices[0].message.content 
#     reply = """
# [
#   {
#     "part": "Outro",
#     "lyrics": [
#       "Here's to the {noun}, the light, and the {noun},",
#       "On this path, we're forever {adjective}.",
#       "From dawn to dusk, under the sky's {noun},",
#       "Together, into the unknown we {verb}."
#     ]
#   }
# ]
# """
    reply = reply.replace("```json", "")
    reply = reply.replace("```", "")
    reply = reply.strip()
    print(f"ChatGPT: {reply}") 
    manager.currentLyrics = reply
    # parse out information about the response, such as how many inputs there are
    lyrics = json.loads(reply)
    pattern = r'\{.*?\}'
    num_inputs = 0
    for part in lyrics:
        for line in part["lyrics"]:
            matches = re.findall(pattern, line)
            if (matches):
                num_inputs += len(matches)
    manager.num_inputs = num_inputs

    return {
        "event": "lyrics",
        "lyrics": reply
        }

def generate_random_number(upper_limit):
    return random.randrange(0, upper_limit)

def get_random_non_empty_entry(data_dict):
    # Filter out entries with string values longer than 0
    non_empty_entries = {k: v for k, v in data_dict.items() if isinstance(v, str) and len(v) > 0}
    
    # If there are non-empty entries, return a random one
    if non_empty_entries:
        random_key = random.choice(list(non_empty_entries.keys()))
        return non_empty_entries[random_key]
    
    # If all entries are empty or there are no entries, return None
    return None