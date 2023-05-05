import os
import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry
from tqdm import tqdm
import pylrc
import json
from PIL import Image
from multiprocessing import Pool, Manager,Lock, Value
from mutagen.easyid3 import EasyID3
from mutagen.id3 import APIC, SYLT, Encoding, ID3
from mutagen.flac import Picture, FLAC
from pydub import AudioSegment
import time
import datetime
import sys
import random
def make_valid(filename):
    # Make a filename valid in different OSs
    f = filename.replace(':', '_')
    f = f.replace('/', '_')
    f = f.replace('<', '_')
    f = f.replace('>', '_')
    f = f.replace('\'', '_')
    f = f.replace('\\', '_')
    f = f.replace('|', '_')
    f = f.replace('?', '_')
    f = f.replace('*', '_')
    return f


def lyric_file_to_text(filename):
    lrc_file = open(filename, 'r', encoding='utf-8')
    lrc_string = ''.join(lrc_file.readlines())
    lrc_file.close()
    subs = pylrc.parse(lrc_string)
    ret = []
    for sub in subs:
        time = int(sub.time * 1000)
        text = sub.text
        ret.append((text, time))
    return ret

def update_downloaded_albums(queue, directory):
    while 1:
        album_name = queue.get()
        try:
            with open(directory + 'completed_albums.json', 'r', encoding='utf8') as f:
                completed_albums = json.load(f)
        except:
            completed_albums = []
        completed_albums.append(album_name)
        with open(directory + 'completed_albums.json', 'w+', encoding='utf8') as f:
            json.dump(completed_albums, f)


def fill_metadata(filename, filetype, album, title, albumartist, artist, tracknumber, albumcover, songlyricpath):
    if filetype == '.mp3':
        file =  EasyID3(filename)
    else:
        file = FLAC(filename)

    file['album'] = album
    file['title'] = title
    file['albumartist'] = ''.join(albumartist)
    file['artist'] = ''.join(artist)
    file['tracknumber'] = str(tracknumber + 1)
    file.save()

    if filetype == '.mp3':
        file = ID3(filename)
        file.add(APIC(mime='image/png',type=3,desc='Cover',data=open(albumcover,'rb').read()))
        # Read and add lyrics
        if (songlyricpath != None):
            sylt = lyric_file_to_text(songlyricpath)
            file.setall('SYLT', [SYLT(encoding=Encoding.UTF8, lang='eng', format=2, type=1, text=sylt)])
        file.save()
    else:
        image = Picture()
        image.type = 3
        image.desc = 'Cover'
        image.mime = 'image/png'
        with open(albumcover,'rb') as f:
            image.data = f.read()
        with Image.open(albumcover) as imagePil:
            image.width, image.height = imagePil.size
            image.depth = 24
        file.add_picture(image)
        # Read and add lyrics
        if (songlyricpath != None):
            musiclrc = open(songlyricpath, 'r', encoding='utf-8').read()
            file['lyrics'] = musiclrc
        file.save()

    return 



def download_song(session, directory, name, url, song_counter, lock,file_format):
    # Set timeout and retry parameters
    time.sleep(3)
    timeout = 10
    retries = 5

    source = session.get(url, stream=True)
    filename = directory + '/' + make_valid(name)
    filetype = ''

    if source.headers['content-type'] == 'audio/mpeg':
        filename += '.mp3'
        filetype = '.mp3'
    else:
        filename += '.wav'

    # Download song with retries and timeout
    total = int(source.headers.get('content-length', 0))
    downloaded = 0
    retry_count = 0
    while downloaded < total:
        try:
            with open(filename, 'ab') as f, tqdm(
                desc=name,
                total=total,
                initial=downloaded,
                unit='iB',
                unit_scale=True,
                unit_divisor=1024,
            ) as bar:
                f.seek(downloaded)
                for data in source.iter_content(chunk_size = 1024):
                    size = f.write(data)
                    downloaded += size
                    bar.update(size)
                    if downloaded >= total:
                        break
                    if retry_count > 0:
                        print(f'Retry successful. Downloading {name}...')
                    retry_count = 0
        except (requests.exceptions.RequestException, IOError) as e:
            if retry_count >= retries:
                raise e
            else:
                retry_count += 1
                print(f"Download of {name} failed. Retrying in 3 seconds ({retry_count}/{retries})", file=sys.stderr)
                time.sleep(3)
                source = session.get(url, stream=True, timeout=timeout)
                total = int(source.headers.get('content-length', 0))
                downloaded = f.tell()

        if downloaded < total:
            print(f'Download of {name} was incomplete. Retrying...', file=sys.stderr)
            os.remove(filename)
        
        # Increase song counter
        with lock:
            song_counter.value += 1

    # If file is .wav then export to .flac
    if source.headers['content-type'] != 'audio/mpeg':
        filename, filetype = choice_format(file_format,filename,directory,name)

        
    return filename, filetype


# define a function to make a valid file name
def choice_format(file_format,filename,directory,name):
    # implementation details here

    # check the input and perform the conversion
    if file_format == 'flac':
        # convert to FLAC
        AudioSegment.from_wav(filename).export(directory + '/' + make_valid(name) + '.flac', format='flac')
        os.remove(filename)
        filename = directory + '/' + make_valid(name) + '.flac'
        filetype = '.flac'
    elif file_format == 'mp3':
        # convert to MP3
        AudioSegment.from_wav(filename).export(directory + '/' + make_valid(name) + '.mp3', format='mp3')
        os.remove(filename)
        filename = directory + '/' + make_valid(name) + '.mp3'
        filetype = '.mp3'
    else:
        print("Invalid file format. Please enter 'flac' or 'mp3'.")
    
    return filename, filetype

def download_album( args, pass_counter, song_counter, album_counter,lock,file_format):
    directory = args['directory']
    session = args['session']
    queue = args['queue']
    album_cid = args['cid']
    album_name = args['name']
    album_coverUrl = args['coverUrl']
    album_artistes = args['artistes']
    album_url = 'https://monster-siren.hypergryph.com/api/album/' + album_cid + '/detail'



    try:
        with open(directory + 'completed_albums.json', 'r', encoding='utf8') as f:
            completed_albums = json.load(f)
    except:
        completed_albums = []

    # fix the album name which have space in last word in Windows
    album_name = album_name.rstrip().split()
    if len(album_name) > 0 and album_name[-1].endswith(' '):
        album_name[-1] = album_name[-1][:-1]
    album_name = ' '.join(album_name)

    if album_name in completed_albums:
        # If album is completed then skip
        print(f'Skipping downloaded album {album_name}')
        with lock:
            pass_counter.value += 1
        return
    try:
        os.mkdir(directory + album_name)
    except:
        pass
    
    # Download album art
    with open(directory + album_name + '/cover.jpg', 'w+b') as f:
        f.write(session.get(album_coverUrl).content)

    # Change album art from .jpg to .png
    cover = Image.open(directory + album_name + '/cover.jpg')
    cover.save(directory + album_name + '/cover.png')
    os.remove(directory + album_name + '/cover.jpg')


    songs = session.get(album_url, headers={'Accept': 'application/json'}).json()['data']['songs']
    for song_track_number, song in enumerate(songs):
        # Get song details
        time.sleep(3)  # add 3-second delay
        song_cid = song['cid']
        song_name = song['name']
        song_artists = song['artistes']
        song_url = 'https://monster-siren.hypergryph.com/api/song/' + song_cid
        headers = read_agent()
        song_detail = session.get(song_url, headers=headers).json()['data']
        song_lyricUrl = song_detail['lyricUrl']
        song_sourceUrl = song_detail['sourceUrl']

        # Download lyric
        if (song_lyricUrl != None):
            songlyricpath = directory + album_name + '/' + make_valid(song_name) + '.lrc'
            with open(songlyricpath, 'w+b') as f:
                f.write(session.get(song_lyricUrl).content)
        else:
            songlyricpath = None

        # Download song and fill out metadata
        filename, filetype = download_song(session=session, directory=directory + album_name, name=song_name, url=song_sourceUrl,song_counter=song_counter,lock=lock,file_format=file_format)
        fill_metadata(filename=filename,
                        filetype=filetype,
                        album=album_name,
                        title=song_name,
                        albumartist=album_artistes,
                        artist=song_artists,
                        tracknumber=song_track_number,
                        albumcover=directory + album_name + '/cover.png',
                        songlyricpath=songlyricpath)

    # Increase album counter
    with lock:
        album_counter.value += 1
    # Mark album as finished
    queue.put(album_name) 
    return 

def read_agent():
    # Read user agent strings from file
    with open('user_agent.txt', 'r') as f:
        user_agent_list = [line.strip() for line in f]

    # Choose a random user agent
    user_agent = random.choice(user_agent_list)

    # Set headers with Accept and User-Agent
    headers = {
        'Accept': 'application/json',
        'User-Agent': user_agent
    }
    return headers


def main():
    directory = './MonsterSiren/'
    session = requests.Session()
    manager = Manager()
    queue = manager.Queue()
    lock = manager.Lock()
    pass_counter = manager.Value('i', 0)
    song_counter = manager.Value('i', 0)
    album_counter = manager.Value('i', 0)

    file_format = input("Enter the file format to convert to (flac/mp3): ")

    try:
        os.mkdir(directory)
    except:
        pass


    headers = read_agent()
    # Get all albums
    albums = session.get('https://monster-siren.hypergryph.com/api/albums', headers=headers).json()['data']
    for album in albums:
        album['directory'] = directory
        album['session'] = session
        album['queue'] = queue


    # Download all albums
    num_workers = os.cpu_count() - 3  # leave CPU core free
    with Pool(num_workers) as pool:
    # with Pool(maxtasksperchild=1) as pool:
        pool.apply_async(update_downloaded_albums, (queue, directory))
        results = pool.starmap(download_album, [(album, pass_counter, song_counter, album_counter, lock, file_format) for album in albums])
        queue.put('kill')
    
    pass_total = pass_counter.value
    song_total = song_counter.value
    album_total = album_counter.value
    # Write counter to file
    with open("Statistics.txt", "a") as f:
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        f.write(f'Finish Time: {timestamp}\n')
        f.write(f'Total albums skipped: {pass_total}\n')
        f.write(f"Downloaded {song_total} songs from {album_total} albums.\n")
        f.write(f"-----------------------------\n")
    print(f'Total albums skipped: {pass_total}')
    print(f"Downloaded {song_total} songs from {album_total} albums.")
    return



if __name__ == '__main__':
    main()
