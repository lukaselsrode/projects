import time
import yaml
import csv
import argparse
import pandas as pd
from os import system as run
from subprocess import getoutput as get 
from matplotlib import pyplot as plt

def setup_cfg()->None:
    parser=argparse.ArgumentParser()
    parser.add_argument("-u",type=str,help="the users program",default='default_cfg')
    args=parser.parse_args()
    global USER
    global DAT_FILE
    USER=args.u
    DAT_FILE = f'config/{USER}/data.csv'

# a function to load the yaml files where the users terms are configured
def load_yaml(filename: str) -> dict:
    with open(f'./config/{USER}/{filename}', 'r') as file:
        obj=yaml.safe_load(file)
    return obj

# function to write data to csv file 
def write_data(data:list[float]) -> None:
    with open(DAT_FILE, 'a') as f:
        writer = csv.writer(f)
        writer.writerow(data)

# function to get todays date
def get_date() -> str:
    return "-".join([str(i) for i in time.localtime()[:3]])

# function to check if the day is valid
def new_entry_valid()-> bool:
    return False if str(get(f"tail -n 1 {DAT_FILE} | cut -d ',' -f 1")) == get_date() else True
                
# something to prompt user  
def get_answer(question: str) -> int:
    print(f'Input [Y/N] ~ {question}')
    ans=str(input())
    return 1 if 'y' in ans or 'Y' in ans else 0

# get mean score given a set/list of questions 
def return_mean_term(questions:list[str]) -> int or float:
    return round(sum(list(map(lambda x:get_answer(x), questions)))/len(questions),3)

# function to create a set of questions from lists in config
def create_field_questions(prefix:str,entries:list[str],suffix:str)->list[str]:
    if not suffix: suffix = '?'
    return list(map(lambda x: ' '.join([prefix,x,suffix]),entries))

# function to create all the questions for any config file
def ask_questions(cfg_file:str,prompts_cfg:list[tuple[str,str,str or None]]) -> list[str]:
    file,q=load_yaml(cfg_file),[]
    for pre,field,suf in prompts_cfg:q+=create_field_questions(pre,file[field],suf)
    return return_mean_term(q)

# Measuring Willpower
def will_power() -> float:
    return ask_questions('wp.yaml',[('Do you want to','desires',None)])

# Negative Reinforcement
def neg_reinforcement() -> float:
    dq_args,dr_args=list(tuple(zip(['Are you']*3,['restrictions','boundaries','accountability'],3*[None]))),[('Have you','relapse',None)]
    return ask_questions('nr.yaml',dq_args+dr_args)

# Obssesion 
def obsession()->float:
    args=[
        ('Did you forget to take your medication to manage','mental',None),
        ('Are you addicted to','addiction',None)     
    ]
    return ask_questions('o.yaml',args)  

def pos_reinforcement()->float:
    args = [
        ('Have you lived in accordance with','values',None),
        ('Have you done your daily','daily',None),
        ('Have you been a part of a','fellowship','fellowship today?')]
    return ask_questions('pr.yaml',args)

## TODO: 
def measure_daily_program() -> None:    
    if new_entry_valid():
        day = get_date()
        wp,nr,o,pr = will_power(),neg_reinforcement(),obsession(),pos_reinforcement()
        p = wp+nr-(o-pr)
        run('clear')
        print(f'JUST FOR TODAY ~ {day}\n\nWill Power: {wp} | Negative Reinforcement: {nr} | Obsesion: {o} | Positive Reinforcement: {pr}')
        print(f'Program Value: {p}')
        write_data([day,wp,nr,o,pr,p])
        return
    print('Program Value for Today is already recorded...')
    

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
    setup_cfg(),measure_daily_program(),show_progress()    



if __name__ == '__main__':
    main()