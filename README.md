Fixed from 1n0r1

Already test for using on Ubuntu & Windows in Python 3.  
Download all songs, albums and fill out metadata, album, cover art, artists and even lyrics.  

### Fix and add function

- Add the retry for the song didn't download for 100%
- Add the timeout connection and retry function
- Add the counter in the multiprocess to count the songs and album
- Fix the tool use on Windows will be false because the album name have the space in the last
- Add the delay in every download active
- Add the User Agent to avoid the Program identify is a crawler
- Add the choice to choose which the format of song or download all for flac and mp3

### Falsed to accomplish

- [ ] retry to print the retry message.  
(Think may the message should add in the tqdm)   

### Note:

The API offers .mp3 and .wav, but the program convert .wav to .flac or .mp3 since .wav can't do metadata.  

### Requirements:

Python

ffmpeg

```
requests
tqdm
mutagen
pydub
pathvalidate
pylrc
Pillow
```

```pip3 install -r requirements.txt``` or ```pip install -r requirements.txt```

### Runs:

- ```python3 main.py``` or ```python main.py```

- ```Enter the format of the song, mp3 ,flac or all ( The songs offers .mp3 and .wav, the program will convert .wav to .flac or .mp3 since .wav can't do metadata. )```

- ```Choose the all for download the song all for mp3 and flac by transfer from wav.```

