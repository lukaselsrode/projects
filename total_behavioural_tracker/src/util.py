import os
import time
import json
import csv
import pandas as pd
from matplotlib import pyplot as plt
import seaborn as sns
from pathlib import Path
from kivy.app import App


def find_file(filename):
    file_path = os.path.join(App.get_running_app().user_data_dir, "data", filename)
    file = Path(file_path)
    if not file.exists():
        raise FileNotFoundError(f"Configuration file not found: {file}")
    return file


def load_json(filename) -> dict:
    with open(filename,'r') as file:
        return json.load(file)


def write_data(data, filename):
    with open(filename,'w') as file:
        return json.dump(data, file)

############################################################################
def get_dat_file():
    return find_file("program_data.csv")

def get_img_file():
    return find_file("program_graph.png")

def get_app_cfg():
    return load_json(find_file("app_config.json"))

def get_program_cfg():
    return load_json(find_file("program_cfg.json"))

### SO MANY ISSUES HERE ....
PlotCFG, ClassesCFG, MeasureCFG, ConfigCFG, AboutCFG, MCFG = (
    GlobalCFG["util"]["plot"],
    GlobalCFG["classes"],
    GlobalCFG["measure"],
    GlobalCFG["cfg"],
    GlobalCFG["about"],
    GlobalCFG["main"],
)


def load_variable_data(varname) -> dict:
    return ProgramCFG[varname]


def update_var_key_data(var_name: str, key: str, new_data: list) -> None:
    temp = {}
    for var in ProgramCFG.keys():
        temp[var] = ProgramCFG[var]
        if var == var_name:
            temp[var][key]["user"] = new_data
    write_data(temp, get_program_cfg())


def unconfigured_vars():
    vars, unconfigured = (
        list(ProgramCFG.keys()),
        [],
    )
    for v in vars:
        for v in load_variable_data(v).values():
            if not v["user"]:
                unconfigured.append(v)
    return unconfigured


def store_measurement(data: list) -> None:
    towrite = [get_date()] + data
    with open(get_dat_file(), "a+", newline="") as f:
        writer = csv.writer(f)
        writer.writerow("%s\n" % towrite)


def get_date() -> str:
    return "-".join([str(i) for i in time.localtime()[:3]])


def new_entry_valid() -> bool:
    df = get_formatted_df()
    if df.empty:
        return True
    l_row = df.index[-1]
    last_entry_today = (
        str(l_row).split()[0] == str(pd.to_datetime(get_date())).split()[0]
    )
    return False if last_entry_today else True


def overwrite_last_entry() -> None:
    df = get_formatted_df()
    df = df.drop(df.index[-1])
    df.to_csv(get_dat_file())


def create_field_questions(prefix: str, entries: list, suffix: str) -> list:
    if not suffix:
        suffix = "?"
    return list(map(lambda x: " ".join([prefix, x, suffix]), entries))


def mk_questions(cfg_file: str, prompts_cfg: list) -> list:
    file, q = load_variable_data(cfg_file), []
    for pre, field, suf in prompts_cfg:
        q += create_field_questions(pre, file[field]["user"], suf)
    return q


def will_power() -> float:
    return mk_questions("willpower", [("Do you want to", "Desires", None)])


def neg_reinforcement() -> float:
    dq_args, dr_args = list(
        tuple(
            zip(
                ["Are you"] * 3,
                ["Restrictions", "Boundaries", "Accountability"],
                3 * [None],
            )
        )
    ), [("Have you", "Relapse", None)]
    return mk_questions("negative reinforcement", dq_args + dr_args)


def obsession() -> float:
    args = [
        ("Did you forget to take your medication to manage", "Mental", None),
        ("Are you addicted to", "Addiction", None),
    ]
    return mk_questions("obsession", args)


def pos_reinforcement() -> float:
    args = [
        ("Have you lived in accordance with", "Values", None),
        ("Have you done your daily", "Daily", None),
        ("Have you been a part of a", "Fellowship", "fellowship today?"),
    ]
    return mk_questions("positive reinforcement", args)


def normalize_as_pct(
    val: float or int, min_val: float or int, val_range: float or int
) -> int:
    return round(100 * ((val - min_val) / val_range))


def get_formatted_df() -> pd.DataFrame:
    df = pd.read_csv(get_dat_file())
    ys = [i for i in df.columns if i != "date"]
    df.set_index("date", inplace=True)
    if not df.empty:
        df.index = pd.to_datetime(df.index, yearfirst=True)
        df = df[ys]
    else:
        df = pd.DataFrame(columns=ys)
        df.index = pd.to_datetime([])
    return df


def get_warn_index(df):
    df_index = df.index
    min_date, max_date = min(df_index), max(df_index)
    return min_date + (PlotCFG["warning"]["offset_dist"] * (max_date - min_date))


def set_plot_options(df: pd.DataFrame) -> None:
    WARN = PlotCFG["warning"]
    LEG = PlotCFG["legend"]
    AXES = PlotCFG["axes"]
    sns.set_theme(context="notebook", style="darkgrid", palette="muted")
    if not df.empty:
        df.plot(style=["ms-", "go-", "y^-", "bs-", "rs-"])
        plt.text(
            x=get_warn_index(df),
            y=15,
            s="Relapse Danger Zone",
            fontsize=WARN["font_size"],
            va="center",
            ha="center",
        )
        plt.axhspan(ymin=0, ymax=25, color=WARN["color"], alpha=WARN["opacity"])
        plt.legend(loc=LEG["loc"], fontsize=LEG["font_size"])
    plt.xlabel("Time", fontsize=AXES["font_size"])
    plt.ylabel("Total % Value", fontsize=AXES["font_size"])

    ax = plt.gca()
    ax.tick_params(axis="x", labelsize=AXES["tick_font_size"])
    ax.tick_params(axis="y", labelsize=AXES["tick_font_size"])


def store_daily_visualization() -> None:
    df = get_formatted_df()
    set_plot_options(df)
    plt.savefig(get_img_file())


def update_reccords(data) -> None:
    store_measurement(data)
    store_daily_visualization()
