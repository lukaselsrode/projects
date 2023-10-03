# Terminal Game: ASCII Driver

## Inspiration
I recently watched the Tetris Movie (2023). I liked that the movie showed how the original conception of tetris 
only used the ascii characters of '[]' to make up the main tetra blocks that comprised all of the functional units of the game-world. A portion of the movie, showed the protagonists 
in a high-speed car chase with the KGB through the streets of Moscow. That portion of the movie then flickered back and forth between realtiy 
and an ascii character video game representation of the chase sequence. Part of me went "ah-ha! what a neat little concept for a toy-ascii game", I went hunting throgh the interwebs and while 
old-school 8/16-bit racers  like pole-position were a plenty I was amiss to find anything that had that classic ascii style that might be classified as an "ascii racer", so I made one. I challenged myself 
to write everything in the game from scratch and really on as few packages as possible, in the same spirit in which the original Tetris was written.

## Overview
### Video
![]
### Mechanics
#### Main Game Loop
I did some reading into how most games relly on a 'main gamplay loop'
```python
    def game():
        road,user_stdin,start_time=Road(),KeyListner(),time.time()
        while True:
            curr_time = time.time()
            process_inputs(user_stdin,road),update(road),render(road,curr_time,start_time)            
```
#### Object Orientated Implementation
##### KeyListener
##### Game
##### Player
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

