# Terminal Game: ASCII Driver

## Inspiration
I recently watched the Tetris Movie (2023). I liked that the movie showed how the original conception of Tetris 
only used the ascii characters of '[]' to make up the main tetra blocks that comprised all of the functional units of the game-world. A portion of the movie, showed the protagonists 
in a high-speed car chase with the KGB through the streets of Moscow. That portion of the movie then flickered back and forth between reality 
and an ascii character video game representation of the chase sequence. Part of me went "ah-ha! what a neat little concept for a toy-ascii game", I went hunting through the interwebs and while 
old-school 8/16-bit racers  like pole-position were a plenty I was amiss to find anything that had that classic ascii style that might be classified as an "ascii racer", so I made one. I challenged myself 
to write everything in the game from scratch and rely on as few packages as possible, in the same spirit in which the original Tetris was written.

## Overview
![](https://github.com/lukaselsrode/projects/blob/main/game_dev/ascii_driver/misc/game_video.gif)

## Install
### Auto-install Script
Run this shell script to install the game to the directory you run the script from. I would suggest somewhere in /usr/local/. 
```shell
    git clone https://github.com/lukaselsrode/projects.git; 
    mv projects/game_dev/ascii_driver/ ./;
    rm -rf ./projects;
    pip install -r ./ascii_driver/requirements.txt;
    alias asciidriver="/usr/bin/python $PWD/ascii_driver/game.py"
```
### PlayGame Locally
Now you can play the game on your terminal running the command
```shell
    $ asciidriver
```
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
##### KeyListener
The Game.process_inputs() method is implemented with a KeyListener using the [pynput](https://pypi.org/project/pynput/) library. This method was easy to implement given that the only real inputs I needed to keep track of was the two possible directional keys and the escape key to quit the program. 
```python
class KeyListner(object):
    def __init__(self):
        self.direction,self.quit=None,False
        keyboard.Listener(on_press=lambda x : self.process_key(x)).start()
```
##### Settings
This class is used to configure the game settings, the frame-rate refresh, the number of lanes on the road. It keeps track of the 'levels' and takes in a default configuration defined in the first lines of game.py; this could be moved to a YAML or JSON to be a little cleaner but I liked the idea of the game being self-contained in one file. 
```python
class Settings(object):
    def __init__(self):
        self.game_world=self.window_len,self.edge_char,self.mid_char,self.open_char,self.secs_per_lvl = DEFAULT_WINDOW_LENGTH,'_', '- ',' ',DEFAULT_TIME_PER_LVL
        self.rules=DEFAULT_RULES_SET
        self.nlanes=self.asset_spawn_time=self.max_n_assets=self.pot_pwrup=self.t_per_frame=self.asset_jump_time=None
        self.lvl=0
```
##### Road
Most of the game logic is done in the Road Class including collision detection and object creation and destruction. This might be a 'GameLogic' and 'World' class in traditional game development.However, I decided to not segment the logic given the scope of the project was relatively small. 
```python
class Road(object):
    def __init__(self):
        self.game_rules,self.assets=Settings(),[]
        self.last_spawn=self.last_lvl=0
```
##### Game
```python
class Game(object):
    def __init__(self):
        self.Keys,self.Road = KeyListner(),Road()
```
The Game class takes the game world objects in the Road class and user input in the KeyListner object and uses it to advance the game. While a traditional application is static, waiting for an input or request to update/return, a game needs to update/return regardless of an input or request. In effect the application needs to update/return even on void inputs. 
##### Player
The player class is the car which the user has control over. The ASCII representation of the player needs to be taken into account as when the car jumps lanes, approaching objects need to be shifted accordingly to the assets size. 
```python
class Player(object):
    def __init__(self,Settings: object):
        self.game_rules,self.power,self.ascii=Settings,None,DEFAULT_PLAYER_CAR                  
        self.sx,self.sy=measure_asset(self.ascii)                               
        self.lane_pos=self.bullet_spacing=0
```
##### Approacher
The Approacher class are the objects which come at the player. Either they are powerups, or they are obstacles which break the main game loop and force a 'GAME OVER'. 
```python
class Approacher(object):
    def __init__(self,is_obstacle:bool,Settings:object):
        self.is_obstacle,self.a_id = is_obstacle,str(id(self))
        self.name,self.ascii=random.choice(OBSTACLES if is_obstacle else POWERUPS)
        self.lane_pos = random.choice([i for i in range(Settings.nlanes*2)])
        self.sx,self.sy = measure_asset(self.ascii)
        self.frame_count,self.last_jumped=self.sx,time.time()
```
### Future Additions 
#### Webpage
In main.py, there is a FLASK implementation for the game. However, the ASCII color codes and terminations I used to make it valid and playable in the terminal are not compatible with a web page. 
As such I would need to implement a color scheme adapted to a web page format, or re-write the game.py file in JavaScript. However I did manage to get the process of running the game to pipe to the page. 
```python
@app.route('/game')
def game():
    proc=subprocess.Popen(['python3','game.py'],stdin=subprocess.PIPE,stdout=subprocess.PIPE)
    while True:
        out=proc.stdout.read().decode()
        if not out: break
        return render_template('game.html',output=out)
```