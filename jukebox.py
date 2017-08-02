# -*- coding: utf-8 -*-
import os
from mpd import MPDClient
import json
import libspotify
import requests
import mac_auth
import time
from threading import Lock
from flask import Flask, render_template, session, request
app = Flask(__name__)

@app.route("/")
def accueil():
    """Renvoie la page d'accueil"""
    return render_template("accueil.html")

maclist_lock = Lock()
maclist = []
@app.route("/sync")
def sync():
    """
    Renvoie quelque choise du type:
    {
   "time":0,
   "playlist":[
      {
         "album":"Fusa",
         "artist":"Macromism",
         "url":"spotify:track:2L4GpAeRotv9jKIMas6lXv",
         "albumart_url":"https://i.scdn.co/image/eef87e5ce12499aa221578056a57e1a82b025609",
         "track":"Untoldyou",
         "duration":"430"
      }
   ]
}
    """

    global maclist, maclist_lock
    mac = mac_auth.get_mac(request.remote_addr)
    now = time.time()
    timeout=120
    new_maclist = []
    found=False
    with maclist_lock:
        for m,t in maclist:
            if m == mac:
                found=True
                new_maclist.append((mac,now))
            elif t > now - timeout:
                new_maclist.append((m,t))
        if found==False:
            new_maclist.append((mac,now))
        maclist=new_maclist

    client = MPDClient()
    client.connect("localhost", 6600)
    status = client.status()
    playlist = client.playlistinfo()
    client.close()
    client.disconnect()

    play = []
    for i in range(len(playlist)):
        # récupération de l'album art
        play.append({
            "url": playlist[i]["file"],
            "duration": playlist[i]["time"],
            "artist": playlist[i]["artist"],
            "album": playlist[i]["album"],
            "track": playlist[i]["title"],
            "albumart_url": "static/albumart/" + playlist[i]["file"].split(":")[2]
        })

    # récupération du temps écoulé
    if "elapsed" in status:
        elapsed = int(status["elapsed"].split(".")[0])
    else:
        elapsed = -1
    res = {
        "playlist": play,
        "time": elapsed, # temps actuel
        "maclist": maclist
    }

    return json.dumps(res)

@app.route("/search/<query>", methods=['GET'])
def search(query):
    """
    renvoie une liste de tracks correspondant à la requête depuis divers services
    :return: un tableau contenant les infos que l'on a trouvé
    """

    results = []

    #   demande à Spotify la musique que l'on cherche
    #   WARNING: le serveur répond sous forme de JSON
    r = requests.get("http://api.spotify.com/v1/search", params={
        "q": query,
        "type": "track",
        "market": "FR",
        "limit": 4
    }, headers={"Authorization": "Bearer "+libspotify.get_token()})

    #   Si le serveur nous dit qu'il n'y a pas d'erreur
    if r.status_code != 200:
        raise Exception(r.status, r.reason)

    data = r.json()
    if len(data["tracks"]["items"]) == 0:   #   Si le servuer n'a rien trouvé
        raise Exception("nothing found on spotify")
    for i in data["tracks"]["items"]:   #   Sinon on lit les résultats

        results.append({
            "track": i["name"],
            "artist": i["artists"][0]["name"], # TODO: il peut y avoir plusieurs artistes
            "duration": int(i["duration_ms"])/1000,
            "url": i["uri"],
            "albumart_url": i["album"]["images"][2]["url"],
            "album": i["album"]["name"]
        })
    return json.dumps(results)

@app.route("/add/<url>")
def add(url):
    """
    Ajoute l'url à la playlist
    """
    # récupération de l'album art
    r = requests.get("https://api.spotify.com/v1/tracks/"+url.split(":")[2],
                     headers={"Authorization": "Bearer " + libspotify.get_token()})
    if r.status_code != 200:
        raise Exception(r.status_code, r.reason)
    data = r.json()

    # téléchargement (caching) de l'album art
    os.system("wget "+data["album"]["images"][0]["url"]+" -O static/albumart/" + url.split(":")[2])

    client = MPDClient()
    client.connect("localhost", 6600)
    client.add(url)
    if len(client.playlistinfo()) == 1:
        client.play()
    client.close()
    client.disconnect()
    return "ok"

if __name__ == "__main__":
    client = MPDClient()
    client.connect("localhost", 6600)
    # client.clear() # on vide la liste de requêtes lors du lancement
    client.random(0) # lecture séquentielle
    client.consume(1) # activation de l'option qui mange les pistes au fur et à mesure de la lecture
    client.close()
    client.disconnect()
    app.run(host='0.0.0.0', port=8080)
