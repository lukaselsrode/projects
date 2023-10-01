import time
import yaml
import pandas as pd
import csv
from os import system as run
from subprocess import getoutput as get 
from matplotlib import pyplot as plt

DEFAULT_USER = 'lukas'
DEFAULT_DAT_FILE = f'config/{DEFAULT_USER}/data.csv'

# something to prompt user 
def get_answer(question: str) -> int:
    print(f'Input [Y/N] ~ {question}')
    ans = str(input())
    return 1 if 'y' in ans or 'Y' in ans else 0

# get mean score given a set/list of questions 
def return_mean_term(questions:list[str]) -> int or float:
    return sum(list(map(lambda x:get_answer(x), questions)))/len(questions)

# a function to load the yaml files where the users terms are configured
def load_yaml(filename: str) -> dict:
    with open(f'./config/{DEFAULT_USER}/{filename}', 'r') as file:
        obj = yaml.safe_load(file)
    return obj

# function to get todays date
def get_date() -> str:
    return "-".join([str(i) for i in time.localtime()[:3]])

# functions for the terms
def will_power() -> float:
    wp= load_yaml('wp.yaml')
    questions =  [' '.join([wp['proposition'],i,wp['ending']]) for i in wp['desires']]
    return round(return_mean_term(questions),3)
    
def neg_reinforcement() -> float:
    nr=load_yaml('nr.yaml')
    daily_questions,daily_reflections = [*nr['restrictions'],*nr['boundries'],*nr['accountability']], nr['rellapse']
    daily_questions = [' '.join(['Are you',i,'?']) for i in daily_questions]
    daily_reflections = [' '.join(['Have you',i,'?']) for i in daily_reflections]
    return round(return_mean_term([*daily_questions,*daily_reflections]),3)

def obsession():
    o,q=load_yaml('o.yaml'),[]
    for i in o['mental']:
        q.append(f'forgot to take your meds to manage {i}')
    for i in o['addiction']:
        q.append(f'Are you addicted to {i}?')
    return round(return_mean_term(q),3)        

def pos_reinforcement():
    pr,q=load_yaml('pr.yaml'),[]
    for i in pr['values']:
        q.append(f'have you lived in accordance with {i} ?')
    for i in pr['daily']:
        q.append(f'have you done your daily {i} ?')
    for i in pr['fellowship']:
        q.append(f'have you been a part of a {i} fellowship today?')
    lqs,las = len(q),len(pr['accomplishments'])
    
    return round(return_mean_term(q) + (len(pr['accomplishments'])/(lqs+las)),3)

def new_entry_valid():
    return False if str(get(f"tail -n 1 {DEFAULT_DAT_FILE} | cut -d ',' -f 1")) == get_date() else True
                
# function to write data to csv file 
def write_data(data):
    with open(DEFAULT_DAT_FILE, 'a') as f:
        writer = csv.writer(f)
        writer.writerow(data)


def measure_daily_program():    
    if new_entry_valid():
        day = get_date()
        wp,nr,o,pr = will_power(),neg_reinforcement(),obsession(),pos_reinforcement()
        p = wp+nr-(o-pr)
        run('clear')
        print(f'JUST FOR TODAY ~ {day}\n\nWill Power: {wp} | Negative Reinforcement: {nr} | Obsesion: {o} | Positive Reinforcement: {pr}')
        print(f'Program Value: {p}')
        data = [day,wp,nr,o,pr,p]
        write_data(data)
        return
    print('Program Value for Today is already reccorded...')
    
# function to show data
def show_progress():
    df=pd.read_csv(DEFAULT_DAT_FILE)
    ys = [i for i in df.columns if i != 'date']
    df.set_index('date')
    df.index = pd.to_datetime(df.date,yearfirst=True)
    df = df[ys]
    df.plot()
    plt.title('Sobriety Program Tracker')
    plt.show()

def main():
    measure_daily_program()
    show_progress()    

if __name__ == '__main__':
    main()
