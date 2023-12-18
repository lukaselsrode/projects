import time
import os
import yaml
import csv
import pandas as pd
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

PLOT = CFG['util']['plot']

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


def unconfigured_vars():
    vars,unconfigured = list(map(lambda i: i.split(".")[0], os.listdir(PATHS["vars_dir"]))),[]
    for v in vars:
        for v in load_variable_data(v).values():
            if not v['user']: unconfigured.append(v)
    return unconfigured

def store_measurement(data:list[int]) -> None:
    with open(DAT_FILE, 'a+', newline='') as f:
        if f.read(1) != '\n': f.write('\n')
        writer = csv.writer(f)
        writer.writerow([get_date()] + data)

# function to get todays date
def get_date() -> str:
    return "-".join([str(i) for i in time.localtime()[:3]])
 
def new_entry_valid()-> bool:
    df = get_formatted_df()
    if df.empty : return True
    l_row = df.index[-1]
    last_entry_today = str(l_row).split()[0] == str(pd.to_datetime(get_date())).split()[0]
    return False if last_entry_today else True

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

def get_formatted_df() -> pd.DataFrame:
    df = pd.read_csv(DAT_FILE)
    ys = [i for i in df.columns if i != 'date']
    df.set_index('date', inplace=True)
    if not df.empty:    
        df.index = pd.to_datetime(df.index, yearfirst=True)
        df = df[ys]
    else:
        df = pd.DataFrame(columns=ys)
        df.index = pd.to_datetime([]) 
    return df

def get_warn_index(df):
    df_index = df.index
    min_date,max_date = min(df_index),max(df_index)
    return min_date + 2*(max_date - min_date) / 3

def set_plot_options(df: pd.DataFrame) -> None:
    WARN = PLOT['warning']
    LEG = PLOT['legend']
    AXES = PLOT['axes']
    sns.set_theme(context='notebook', style='darkgrid', palette='muted')
    if not df.empty:       
        df.plot(style=['ms-', 'go-', 'y^-', 'bs-', 'rs-'])
        plt.text(x=get_warn_index(df), y=15, s='Relapse Danger Zone', fontsize=WARN['font_size'], va='center', ha='center')
        plt.axhspan(ymin=0, ymax=25, color=WARN['color'], alpha=WARN['opacity'])
        plt.legend(loc=LEG['loc'], fontsize=LEG['font_size'])
    plt.xlabel('Time', fontsize=AXES['font_size'])
    plt.ylabel('Total % Value', fontsize=AXES['font_size'])

    ax = plt.gca()
    ax.tick_params(axis='x', labelsize=AXES['tick_font_size'])  
    ax.tick_params(axis='y', labelsize=AXES['tick_font_size'])


def store_daily_visualization()->None:
    df=get_formatted_df()
    set_plot_options(df)
    plt.savefig(IMG_FILE)