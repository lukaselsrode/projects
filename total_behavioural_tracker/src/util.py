import time
import yaml
import csv
import pandas as pd
from subprocess import getoutput as get 
from matplotlib import pyplot as plt
import seaborn as sns


# A funtion to load the application configuration specific to each file
def load_cfg()->dict:
    with open('config/app_cfg.yaml','r') as f:
        cfg = yaml.safe_load(f)
    return cfg

CFG = load_cfg()
PATHS = CFG['paths']
DAT_FILE = PATHS['data']
IMG_FILE = PATHS['img']
VARS_DIR = PATHS['vars_dir']
AXES_FONT_SIZE=CFG['util']['axes_font_size']


def reset_user_configs():
    return

def reset_user_files():
    return


# a function to load the yaml files where the users terms are configured
def load_variable_data(varname)->dict:
    # load the data from the file
    with open(''.join([VARS_DIR,varname,'.yaml']),'r') as cfgfile:
        cfg = yaml.safe_load(cfgfile)
    return cfg

def update_var_key_data(var_name:str, key:str, new_data:list[str])->None:
    cfg_file = ''.join([VARS_DIR, var_name, '.yaml'])    
    with open(cfg_file, 'r') as f:
        data = yaml.safe_load(f)
    data[key]['user'] = new_data
    with open(cfg_file, 'w') as f:
        yaml.dump(data, f, default_flow_style=False)

# function to write data to csv file 
def store_measurement(data:list[int]) -> None:
    with open(DAT_FILE, 'a') as f:
        writer = csv.writer(f)
        writer.writerow([get_date()] + data)
    store_daily_visualization()
    
# function to get todays date
def get_date() -> str:
    return "-".join([str(i) for i in time.localtime()[:3]])

# function to check if the day is valid
def new_entry_valid()-> bool:
    return False if str(get(f"tail -n 1 {DAT_FILE} | cut -d ',' -f 1")) == get_date() else True

# function to earase todays measurment
def overwrite_last_entry() -> None:
    df = get_formatted_df()
    df = df.drop(df.index[-1])
    df.to_csv(DAT_FILE)

# function to create a set of questions from lists in config
def create_field_questions(prefix:str,entries:list[str],suffix:str)->list[str]:
    if not suffix: suffix = '?'
    return list(map(lambda x: ' '.join([prefix,x,suffix]),entries))

# function to create all the questions for any config file
def mk_questions(cfg_file:str,prompts_cfg:list[tuple[str,str,str or None]]) -> list[str]:
    file,q=load_variable_data(cfg_file),[]
    for pre,field,suf in prompts_cfg:q+=create_field_questions(pre,file[field]['user'],suf)
    return q

def will_power() -> float:
    return mk_questions('willpower',[('Do you want to','Desires',None)])

def neg_reinforcement() -> float:
    dq_args,dr_args=list(tuple(zip(['Are you']*3,['Restrictions','Boundaries','Accountability'],3*[None]))),[('Have you','Relapse',None)]
    return mk_questions('negative reinforcement',dq_args+dr_args)

def obsession()->float:
    args=[
        ('Did you forget to take your medication to manage','Mental',None),
        ('Are you addicted to','Addiction',None)     
    ]
    return mk_questions('obsession',args)  

def pos_reinforcement()->float:
    args = [
        ('Have you lived in accordance with','Values',None),
        ('Have you done your daily','Daily',None),
        ('Have you been a part of a','Fellowship','fellowship today?')]
    return mk_questions('positive reinforcement',args)

def normalize_as_pct(val:float or int,min_val:float or int,val_range:float or int)->int:
    return round(100*((val - min_val)/val_range))

def get_formatted_df():
    df=pd.read_csv(DAT_FILE)
    ys = [i for i in df.columns if i != 'date']
    df.set_index('date')
    df.index=pd.to_datetime(df.date,yearfirst=True)
    df = df[ys]
    return df


def set_plot_options(df:pd.DataFrame) -> None:
    sns.set_theme(context='notebook',style='darkgrid',palette='muted')
    df.plot(style=['ms-', 'go-', 'y^-', 'bs-', 'rs-'])
    plt.legend(loc='lower right')
    plt.axhspan(ymin=0, ymax=25, color='red', alpha=0.4)
    plt.text(x=df.index[round(len(df.index) / 2)], y=15, s='Relapse Danger Zone', fontsize=12, va='center', ha='center')
    plt.xlabel('Time', fontsize=AXES_FONT_SIZE)
    plt.ylabel('Total % Value', fontsize=AXES_FONT_SIZE)
    plt.savefig(IMG_FILE)


def store_daily_visualization()->None:
    df=get_formatted_df()
    set_plot_options(df),plt.savefig(IMG_FILE)
    
