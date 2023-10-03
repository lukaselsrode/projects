# Terminal Game: ASCII Driver

## Inspiration
I recently watched the Tetris Movie (2023). I liked that the movie showed how the original conception of Tetris 
only used the ascii characters of '[]' to make up the main tetra blocks that comprised all of the functional units of the game-world. A portion of the movie, showed the protagonists 
in a high-speed car chase with the KGB through the streets of Moscow. That portion of the movie then flickered back and forth between reality 
and an ascii character video game representation of the chase sequence. Part of me went "ah-ha! what a neat little concept for a toy-ascii game", I went hunting through the interwebs and while 
old-school 8/16-bit racers  like pole-position were a plenty I was amiss to find anything that had that classic ascii style that might be classified as an "ascii racer", so I made one. I challenged myself 
to write everything in the game from scratch and really on as few packages as possible, in the same spirit in which the original Tetris was written.

## Overview
### Video
![](https://github.com/lukaselsrode/projects/blob/main/game_dev/ascii_driver/misc/game_video.gif)
### Mechanics
#### Main Game Loop
I did some reading into how most games rely on a [gameplay loop](https://gameprogrammingpatterns.com/game-loop.html) and started implemented a 'Game' class. 
From which I was able to take an OOP approach to fill in the methods of each of these methods by design the other classes comprising the game pretty easily.
```python
    def main_game_loop(self):
        start=time.time()
        while True:
            self.process_inputs(),self.update(),self.render(time.time(),start)
```
#### Object Orientated Implementation
##### Game
Most of the game logic is done in the Game Class including collision detection and object creation and destruction. 
```python
class Game(object):
    def __init__(self):
        self.Keys,self.Road = KeyListner(),Road()
```
##### KeyListener
The Game.process_inputs() method is implemented with a KeyListener using the [pynput](https://pypi.org/project/pynput/) library. This method was easy to implement given that the only real inputs I needed to keep track of was the two possible directional keys and the escape key to quit the program. 
```python
class KeyListner(object):
    def __init__(self):
        self.direction,self.quit=None,False
        keyboard.Listener(on_press=lambda x : self.process_key(x)).start()
```
##### Road 
##### Settings 
This class is used to configure the game settings, the frame-rate refresh, the number of lanes on the road. It keeps track of the 'levels' and takes in a default configuration defined in the first lines of game.py; this could be moved to a YAML or JSON to be a little cleaner but I liked the idea of the game being self-contained in one file. 
##### Approacher
## Install
### Clone Repository
```shell
    $  
```
### Requirements
```shell
    $ pip install -r cmd_driver_game/requirements.txt 
```
### Setup Alias 
```shell
    $ alias ascii_driver='/usr/bin/python <PATH_TO_GAME>.game.py'
```

